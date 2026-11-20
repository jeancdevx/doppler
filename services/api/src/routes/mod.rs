use std::collections::BTreeMap;

use axum::extract::{Path, Query, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::IntoResponse;
use axum::routing::{delete, get, post};
use axum::{Json, Router};
use axum_extra::extract::cookie::{Cookie, CookieJar, SameSite};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::config::AppConfig;
use crate::db;
use crate::domain::{
    generate_opaque_id, sanitize_filename, sign_session_token, verify_session_token,
    AudioUrlResponse, ConfirmUploadRequest, CreateUploadRequest, CreateUploadResponse,
    JobDetailDto, JobStatus, JobSummaryDto, LimitsInfo, SessionResponse, UploadTarget,
    SESSION_COOKIE_NAME,
};
use crate::error::ApiError;
use crate::inference::InferenceHealth;
use crate::state::AppState;

pub fn api_router() -> Router<AppState> {
    Router::new()
        .route("/health", get(health))
        .route("/session", get(get_or_create_session).post(get_or_create_session))
        .route("/uploads", post(create_upload))
        .route("/jobs", get(list_jobs))
        .route("/jobs/{job_id}", get(get_job))
        .route("/jobs/{job_id}", delete(delete_job))
        .route("/jobs/{job_id}/confirm", post(confirm_upload))
        .route("/jobs/{job_id}/audio-url", get(get_audio_url))
        .route("/jobs/{job_id}/export", get(export_job))
}

#[derive(Debug, Serialize)]
struct HealthResponse {
    status: &'static str,
    api: &'static str,
    database: &'static str,
    r2_configured: bool,
    r2_reachable: bool,
    queue_active: i64,
    max_queue_depth: i64,
    max_concurrent_inference: usize,
    limits: LimitsInfo,
    inference: Option<InferenceHealth>,
}

fn limits_from_config(cfg: &AppConfig) -> LimitsInfo {
    LimitsInfo {
        allowed_extensions: vec![".wav"],
        max_file_bytes: cfg.max_file_bytes,
        max_duration_seconds: cfg.max_duration_seconds,
        min_window_seconds: 3.0,
        window_seconds: 3.0,
        hop_seconds: 1.5,
        retention_hours: cfg.retention_hours,
        max_queue_depth: cfg.max_queue_depth,
        max_concurrent_inference: cfg.max_concurrent_inference,
    }
}

fn build_session_cookie(session_id: &str, cfg: &AppConfig) -> Cookie<'static> {
    let signed = sign_session_token(session_id, &cfg.session_hmac_secret);
    let is_https = cfg.app_origin.starts_with("https://");
    Cookie::build((SESSION_COOKIE_NAME, signed))
        .path("/")
        .http_only(true)
        .same_site(SameSite::Lax)
        .secure(is_https)
        .max_age(time::Duration::days(7))
        .build()
}

fn extract_verified_session(jar: &CookieJar, cfg: &AppConfig) -> Option<String> {
    let raw = jar.get(SESSION_COOKIE_NAME)?.value();
    verify_session_token(raw, &cfg.session_hmac_secret)
}

async fn resolve_or_create_session(
    jar: CookieJar,
    state: &AppState,
) -> Result<(CookieJar, String), ApiError> {
    if let Some(session_id) = extract_verified_session(&jar, &state.config) {
        db::ensure_session(&state.db, &session_id).await?;
        return Ok((jar, session_id));
    }
    let session_id = generate_opaque_id(16);
    db::ensure_session(&state.db, &session_id).await?;
    let cookie = build_session_cookie(&session_id, &state.config);
    Ok((jar.add(cookie), session_id))
}

async fn require_session(jar: &CookieJar, state: &AppState) -> Result<String, ApiError> {
    let Some(session_id) = extract_verified_session(jar, &state.config) else {
        return Err(ApiError::Unauthorized(
            "Se requiere una sesión válida de Doppler para acceder a este recurso.".to_string(),
        ));
    };
    db::ensure_session(&state.db, &session_id).await?;
    Ok(session_id)
}

async fn health(State(state): State<AppState>) -> Result<Json<HealthResponse>, ApiError> {
    let queue_active = db::count_active_queue(&state.db).await.unwrap_or(0);
    let inference = state.inference.health().await.ok();
    let r2_configured = state.config.r2_configured();
    let r2_reachable = if r2_configured {
        state.r2.check_bucket_reachable().await.is_ok()
    } else {
        false
    };
    let inference_ready = inference.as_ref().map(|h| h.ready).unwrap_or(false);
    let overall = if inference_ready && r2_reachable {
        "ok"
    } else {
        "degraded"
    };

    Ok(Json(HealthResponse {
        status: overall,
        api: "ok",
        database: "ok",
        r2_configured,
        r2_reachable,
        queue_active,
        max_queue_depth: state.config.max_queue_depth,
        max_concurrent_inference: state.config.max_concurrent_inference,
        limits: limits_from_config(&state.config),
        inference,
    }))
}

async fn get_or_create_session(
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

async fn create_upload(
    State(state): State<AppState>,
    jar: CookieJar,
    Json(req): Json<CreateUploadRequest>,
) -> Result<(CookieJar, (StatusCode, Json<CreateUploadResponse>)), ApiError> {
    if !state.config.r2_configured() {
        return Err(ApiError::Config(
            "Las credenciales de Cloudflare R2 no están configuradas en el servidor.".to_string(),
        ));
    }

    let filename = sanitize_filename(&req.filename);
    if !filename.to_ascii_lowercase().ends_with(".wav") {
        return Err(ApiError::Validation(
            "Solo se admiten archivos con extensión .wav.".to_string(),
        ));
    }

    if req.size_bytes == 0 {
        return Err(ApiError::Validation(
            "El archivo seleccionado está vacío (0 bytes).".to_string(),
        ));
    }

    if req.size_bytes > state.config.max_file_bytes {
        return Err(ApiError::LimitExceeded(format!(
            "El tamaño declarado ({} bytes) excede el máximo de {} bytes (25 MiB).",
            req.size_bytes, state.config.max_file_bytes
        )));
    }

    let (jar, session_id) = resolve_or_create_session(jar, &state).await?;

    let recent = db::count_recent_session_uploads(&state.db, &session_id).await?;
    if recent >= state.config.rate_limit_uploads_per_hour {
        return Err(ApiError::RateLimited(
            "Se alcanzó la cuota temporal de cargas para esta sesión. Espera unos minutos."
                .to_string(),
        ));
    }

    let active_queue = db::count_active_queue(&state.db).await?;
    if active_queue >= state.config.max_queue_depth {
        return Err(ApiError::QueueFull(format!(
            "La cola de análisis está llena ({active_queue}/{}). Intenta nuevamente en breve.",
            state.config.max_queue_depth
        )));
    }

    let content_type = normalize_wav_content_type(req.content_type.as_deref());
    let job_id = generate_opaque_id(16);
    let run_id = format!("run_{}", Uuid::new_v4().simple());
    let object_key = state.r2.build_object_key(&session_id, &job_id);

    let presigned_url = state
        .r2
        .presign_put(&object_key, content_type, state.config.presign_put_ttl_seconds)
        .await?;

    let expires_at = db::create_uploading_job(
        &state.db,
        &job_id,
        &run_id,
        &session_id,
        &filename,
        content_type,
        i64::try_from(req.size_bytes)
            .map_err(|_| ApiError::LimitExceeded("tamaño fuera de rango".into()))?,
        &object_key,
        state.config.retention_hours,
    )
    .await?;

    let mut headers = BTreeMap::new();
    headers.insert("Content-Type".to_string(), content_type.to_string());

    let response = CreateUploadResponse {
        job_id,
        run_id,
        status: JobStatus::Uploading,
        upload: UploadTarget {
            method: "PUT",
            url: presigned_url,
            headers,
            expires_in_seconds: state.config.presign_put_ttl_seconds,
        },
        expires_at,
        retention_hours: state.config.retention_hours,
    };

    Ok((jar, (StatusCode::CREATED, Json(response))))
}

fn normalize_wav_content_type(raw: Option<&str>) -> &'static str {
    match raw.map(|s| s.trim().to_ascii_lowercase()).as_deref() {
        Some("audio/x-wav") => "audio/x-wav",
        Some("audio/wave") => "audio/wave",
        _ => "audio/wav",
    }
}

async fn confirm_upload(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
    body: Option<Json<ConfirmUploadRequest>>,
) -> Result<Json<JobDetailDto>, ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let Some(job) = db::get_job_for_session(&state.db, &job_id, &session_id).await? else {
        return Err(ApiError::NotFound("Trabajo no encontrado en esta sesión.".to_string()));
    };

    let current_status = JobStatus::from_db(&job.status);
    match current_status {
        JobStatus::Queued | JobStatus::Analyzing | JobStatus::Completed => {
            // Confirmación idempotente: devuelve el estado actual sin duplicar en cola.
            return Ok(Json(db::build_job_detail(&state.db, job).await?));
        }
        JobStatus::Failed => {
            return Err(ApiError::Conflict(
                "El trabajo ya falló; crea una nueva carga para reintentar.".to_string(),
            ));
        }
        JobStatus::Uploading => {}
    }

    let head = match state.r2.head_object(&job.object_key).await? {
        Some(info) => info,
        None => {
            return Err(ApiError::Validation(
                "El objeto todavía no existe en Cloudflare R2. Completa la subida PUT antes de confirmar."
                    .to_string(),
            ));
        }
    };

    if head.content_length == 0 {
        let _ = state.r2.delete_object(&job.object_key).await;
        let msg = "El archivo subido a R2 tiene 0 bytes y fue eliminado.";
        db::mark_job_failed(&state.db, &job.id, "uploading", "upload_error", msg).await?;
        return Err(ApiError::Validation(msg.to_string()));
    }

    if head.content_length > state.config.max_file_bytes {
        let _ = state.r2.delete_object(&job.object_key).await;
        let msg = format!(
            "El tamaño real en R2 ({} bytes) excede el máximo de {} bytes; el objeto fue eliminado.",
            head.content_length, state.config.max_file_bytes
        );
        db::mark_job_failed(&state.db, &job.id, "uploading", "limit_exceeded", &msg).await?;
        return Err(ApiError::LimitExceeded(msg));
    }

    let actual_size = i64::try_from(head.content_length)
        .map_err(|_| ApiError::LimitExceeded("tamaño fuera de rango".into()))?;
    let client_upload_ms = body.and_then(|Json(b)| b.client_upload_ms);

    let transitioned = db::confirm_upload_and_enqueue(
        &state.db,
        &job.id,
        actual_size,
        head.etag.as_deref(),
        client_upload_ms,
        state.config.max_queue_depth,
    )
    .await?;

    if transitioned {
        state.job_notify.notify_one();
    }

    let updated = db::get_job_for_session(&state.db, &job.id, &session_id)
        .await?
        .ok_or_else(|| ApiError::NotFound("Trabajo no encontrado.".to_string()))?;

    Ok(Json(db::build_job_detail(&state.db, updated).await?))
}

async fn list_jobs(
    State(state): State<AppState>,
    jar: CookieJar,
) -> Result<Json<Vec<JobSummaryDto>>, ApiError> {
    let Some(session_id) = extract_verified_session(&jar, &state.config) else {
        return Ok(Json(Vec::new()));
    };
    let jobs = db::list_jobs_for_session(&state.db, &session_id, 50).await?;
    Ok(Json(jobs))
}

async fn get_job(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
) -> Result<Json<JobDetailDto>, ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let Some(job) = db::get_job_for_session(&state.db, &job_id, &session_id).await? else {
        return Err(ApiError::NotFound("Trabajo no encontrado en esta sesión.".to_string()));
    };
    Ok(Json(db::build_job_detail(&state.db, job).await?))
}

async fn get_audio_url(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
) -> Result<Json<AudioUrlResponse>, ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let Some(job) = db::get_job_for_session(&state.db, &job_id, &session_id).await? else {
        return Err(ApiError::NotFound("Trabajo no encontrado en esta sesión.".to_string()));
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
struct ExportQuery {
    format: Option<String>,
}

async fn export_job(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
    Query(query): Query<ExportQuery>,
) -> Result<impl IntoResponse, ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let Some(job) = db::get_job_for_session(&state.db, &job_id, &session_id).await? else {
        return Err(ApiError::NotFound("Trabajo no encontrado en esta sesión.".to_string()));
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
        .map(|c| if c.is_ascii_alphanumeric() || c == '_' || c == '-' { c } else { '_' })
        .take(64)
        .collect();
    let stem = if safe_stem.is_empty() { "doppler".to_string() } else { safe_stem };

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
            headers.insert(header::CONTENT_TYPE, "text/csv; charset=utf-8".parse().unwrap());
            headers.insert(
                header::CONTENT_DISPOSITION,
                format!("attachment; filename=\"{stem}_doppler.csv\"")
                    .parse()
                    .unwrap(),
            );
            Ok((headers, csv).into_response())
        }
        "json" => {
            let payload = serde_json::to_string_pretty(&detail)
                .map_err(|e| ApiError::Internal(format!("error serializando JSON: {e}")))?;
            let mut headers = HeaderMap::new();
            headers.insert(
                header::CONTENT_TYPE,
                "application/json; charset=utf-8".parse().unwrap(),
            );
            headers.insert(
                header::CONTENT_DISPOSITION,
                format!("attachment; filename=\"{stem}_doppler.json\"")
                    .parse()
                    .unwrap(),
            );
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

async fn delete_job(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
) -> Result<StatusCode, ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let Some(job) = db::get_job_for_session(&state.db, &job_id, &session_id).await? else {
        return Err(ApiError::NotFound("Trabajo no encontrado en esta sesión.".to_string()));
    };

    if state.r2.is_owned_key(&job.object_key) {
        state.r2.delete_object(&job.object_key).await?;
    }
    db::hard_delete_job(&state.db, &job.id).await?;
    Ok(StatusCode::NO_CONTENT)
}
