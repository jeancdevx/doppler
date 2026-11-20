use axum::extract::{Path, Query, State};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode};
use axum::response::IntoResponse;
use axum::Json;
use axum_extra::extract::cookie::CookieJar;
use serde::Deserialize;

use crate::db;
use crate::domain::{AudioUrlResponse, JobDetailDto, JobStatus, JobSummaryDto, SessionResponse};
use crate::error::ApiError;
use crate::maintenance;
use crate::routes::auth::{
    extract_verified_session, limits_from_config, require_session, resolve_or_create_session,
};
use crate::state::AppState;

pub(super) async fn get_or_create_session(
    State(state): State<AppState>,
    jar: CookieJar,
) -> Result<(CookieJar, Json<SessionResponse>), ApiError> {
    let (jar, session_id) = resolve_or_create_session(jar, &state).await?;
    Ok((
        jar,
        Json(SessionResponse {
            session_id,
            limits: limits_from_config(&state.config),
        }),
    ))
}

pub(super) async fn list_jobs(
    State(state): State<AppState>,
    jar: CookieJar,
) -> Result<Json<Vec<JobSummaryDto>>, ApiError> {
    let Some(session_id) = extract_verified_session(&jar, &state.config) else {
        return Ok(Json(Vec::new()));
    };
    let jobs = db::list_jobs_for_session(&state.db, &session_id, 50).await?;
    Ok(Json(jobs))
}

pub(super) async fn get_job(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
) -> Result<Json<JobDetailDto>, ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let Some(job) = db::get_job_for_session(&state.db, &job_id, &session_id).await? else {
        return Err(ApiError::NotFound(
            "Trabajo no encontrado en esta sesión.".to_string(),
        ));
    };
    Ok(Json(db::build_job_detail(&state.db, job).await?))
}

pub(super) async fn get_audio_url(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
) -> Result<Json<AudioUrlResponse>, ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let Some(job) = db::get_job_for_session(&state.db, &job_id, &session_id).await? else {
        return Err(ApiError::NotFound(
            "Trabajo no encontrado en esta sesión.".to_string(),
        ));
    };

    if JobStatus::from_db(&job.status) == JobStatus::Uploading {
        return Err(ApiError::Conflict(
            "El audio aún no ha completado su carga en R2.".to_string(),
        ));
    }

    let url = state
        .r2
        .presign_get(&job.object_key, state.config.presign_get_ttl_seconds)
        .await?;

    Ok(Json(AudioUrlResponse {
        job_id: job.id,
        url,
        expires_in_seconds: state.config.presign_get_ttl_seconds,
        content_type: job.content_type,
    }))
}

#[derive(Debug, Deserialize)]
pub(super) struct ExportQuery {
    format: Option<String>,
}

pub(super) async fn export_job(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
    Query(query): Query<ExportQuery>,
) -> Result<impl IntoResponse, ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let Some(job) = db::get_job_for_session(&state.db, &job_id, &session_id).await? else {
        return Err(ApiError::NotFound(
            "Trabajo no encontrado en esta sesión.".to_string(),
        ));
    };
    if JobStatus::from_db(&job.status) != JobStatus::Completed {
        return Err(ApiError::Conflict(
            "Solo es posible exportar trabajos completados.".to_string(),
        ));
    }
    let detail = db::build_job_detail(&state.db, job).await?;
    let safe_stem: String = detail
        .filename
        .trim_end_matches(".wav")
        .trim_end_matches(".WAV")
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '_' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .take(64)
        .collect();
    let stem = if safe_stem.is_empty() {
        "doppler".to_string()
    } else {
        safe_stem
    };

    match query.format.as_deref().unwrap_or("json") {
        "csv" => {
            let mut csv = String::from(
                "job_id,run_id,filename,audio_sha256,model_sha256,contract_version,threshold,window_index,start_seconds,end_seconds,score,label,margin_vs_threshold\n",
            );
            let audio_sha = detail.audio_sha256.as_deref().unwrap_or("");
            let model_sha = detail.model_sha256.as_deref().unwrap_or("");
            let contract_ver = detail.contract_version.as_deref().unwrap_or("");
            let threshold = detail.threshold.unwrap_or(0.6547843813896179);
            let escaped_name = csv_escape(&detail.filename);
            for w in &detail.windows {
                csv.push_str(&format!(
                    "{},{},{},{},{},{},{:.16},{},{:.4},{:.4},{:.8},{},{:.8}\n",
                    detail.job_id,
                    detail.run_id,
                    escaped_name,
                    audio_sha,
                    model_sha,
                    contract_ver,
                    threshold,
                    w.index,
                    w.start_seconds,
                    w.end_seconds,
                    w.score,
                    w.label,
                    w.margin_vs_threshold
                ));
            }
            let mut headers = HeaderMap::new();
            headers.insert(
                header::CONTENT_TYPE,
                HeaderValue::from_static("text/csv; charset=utf-8"),
            );
            let disp = HeaderValue::from_str(&format!(
                "attachment; filename=\"{stem}_doppler.csv\""
            ))
            .map_err(|e| ApiError::Internal(format!("encabezado inválido: {e}")))?;
            headers.insert(header::CONTENT_DISPOSITION, disp);
            Ok((headers, csv).into_response())
        }
        "json" => {
            let payload = serde_json::to_string_pretty(&detail)
                .map_err(|e| ApiError::Internal(format!("error serializando JSON: {e}")))?;
            let mut headers = HeaderMap::new();
            headers.insert(
                header::CONTENT_TYPE,
                HeaderValue::from_static("application/json; charset=utf-8"),
            );
            let disp = HeaderValue::from_str(&format!(
                "attachment; filename=\"{stem}_doppler.json\""
            ))
            .map_err(|e| ApiError::Internal(format!("encabezado inválido: {e}")))?;
            headers.insert(header::CONTENT_DISPOSITION, disp);
            Ok((headers, payload).into_response())
        }
        other => Err(ApiError::Validation(format!(
            "Formato de exportación no admitido: {other}. Usa json o csv."
        ))),
    }
}

fn csv_escape(s: &str) -> String {
    if s.contains(',') || s.contains('"') || s.contains('\n') {
        format!("\"{}\"", s.replace('"', "\"\""))
    } else {
        s.to_string()
    }
}

pub(super) async fn delete_job(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
) -> Result<StatusCode, ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let Some(job) = db::get_job_for_session(&state.db, &job_id, &session_id).await? else {
        return Err(ApiError::NotFound(
            "Trabajo no encontrado en esta sesión.".to_string(),
        ));
    };

    if state.r2.is_owned_key(&job.object_key) {
        state.r2.delete_object(&job.object_key).await?;
    }
    let _ = maintenance::mark_telemetry_user_deleted(
        &state.db,
        &job.id,
        state.config.telemetry_redact_on_user_delete,
    )
    .await;
    db::hard_delete_job(&state.db, &job.id).await?;
    Ok(StatusCode::NO_CONTENT)
}
