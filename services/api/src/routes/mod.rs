mod admin;
mod auth;
mod feedback;
mod health;
mod jobs;
mod uploads;

use axum::routing::{delete, get, patch, post};
use axum::Router;

use crate::state::AppState;

pub fn api_router() -> Router<AppState> {
    Router::new()
        // Salud y readiness (compatibles con consumidores existentes + semántica HTTP estricta)
        .route("/health", get(health::health))
        .route("/ready", get(health::ready))
        // Flujos de usuario (sesión anónima HMAC)
        .route(
            "/session",
            get(jobs::get_or_create_session).post(jobs::get_or_create_session),
        )
        .route("/uploads", post(uploads::create_upload))
        .route("/jobs", get(jobs::list_jobs))
        .route("/jobs/{job_id}", get(jobs::get_job))
        .route("/jobs/{job_id}", delete(jobs::delete_job))
        .route("/jobs/{job_id}/confirm", post(uploads::confirm_upload))
        .route("/jobs/{job_id}/audio-url", get(jobs::get_audio_url))
        .route("/jobs/{job_id}/export", get(jobs::export_job))
        // Canal de retroalimentación del propietario de sesión
        .route(
            "/jobs/{job_id}/feedback",
            get(feedback::list_job_feedback).post(feedback::create_job_feedback),
        )
        // Endpoints administrativos protegidos mediante X-Admin-Token
        .route("/admin/overview", get(admin::admin_overview))
        .route("/admin/health/probe", post(admin::admin_probe_now))
        .route(
            "/admin/maintenance",
            get(admin::admin_get_maintenance).post(admin::admin_set_maintenance),
        )
        .route("/admin/drift", get(admin::admin_get_drift))
        .route(
            "/admin/drift/reference",
            post(admin::admin_import_drift_reference),
        )
        .route("/admin/drift/evaluate", post(admin::admin_evaluate_drift))
        .route("/admin/feedback", get(admin::admin_list_feedback))
        .route(
            "/admin/feedback/{report_id}",
            patch(admin::admin_update_feedback),
        )
        .route("/admin/deployments", post(admin::admin_record_deployment))
}
