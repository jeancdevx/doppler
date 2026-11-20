use std::collections::BTreeMap;

use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Json;
use axum_extra::extract::cookie::CookieJar;
use uuid::Uuid;

use crate::db;
use crate::domain::{
    generate_opaque_id, sanitize_filename, ConfirmUploadRequest, CreateUploadRequest,
    CreateUploadResponse, JobDetailDto, JobStatus, UploadTarget,
};
use crate::error::ApiError;
use crate::maintenance;
use crate::routes::auth::{require_session, resolve_or_create_session};
use crate::state::AppState;

pub(super) async fn create_upload(
    State(state): State<AppState>,
    jar: CookieJar,
    Json(req): Json<CreateUploadRequest>,
) -> Result<(CookieJar, (StatusCode, Json<CreateUploadResponse>)), ApiError> {
    let maint = maintenance::get_maintenance_state(&state.db).await?;
    if maint.enabled {
        let reason = maint
            .reason
            .unwrap_or_else(|| "Actualización o mantenimiento controlado en curso.".to_string());
        return Err(ApiError::Maintenance(reason));
    }

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

pub(super) async fn confirm_upload(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
    body: Option<Json<ConfirmUploadRequest>>,
) -> Result<Json<JobDetailDto>, ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let Some(job) = db::get_job_for_session(&state.db, &job_id, &session_id).await? else {
        return Err(ApiError::NotFound(
            "Trabajo no encontrado en esta sesión.".to_string(),
        ));
    };

    let current_status = JobStatus::from_db(&job.status);
    match current_status {
        JobStatus::Queued | JobStatus::Analyzing | JobStatus::Completed => {
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
