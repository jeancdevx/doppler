use axum::extract::{Path, Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::Json;
use serde::{Deserialize, Serialize};

use crate::db;
use crate::error::ApiError;
use crate::maintenance::{
    self, AdminFeedbackListDto, AdminOverviewDto, DriftEvaluationDto, DriftReferencePayload,
    DriftReferenceSummary, DriftStatusResponseDto, FeedbackReportDto, LiveProbeResult,
    MaintenanceStateDto, ModelDeploymentRow, RecordDeploymentRequest, UpdateFeedbackRequest,
};
use crate::routes::auth::require_admin;
use crate::state::AppState;

#[derive(Debug, Deserialize)]
pub(super) struct WindowQuery {
    days: Option<i64>,
}

pub(super) async fn admin_overview(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(query): Query<WindowQuery>,
) -> Result<Json<AdminOverviewDto>, ApiError> {
    require_admin(&headers, &state.config)?;
    let days = query.days.unwrap_or(30).clamp(1, 365);
    let overview = maintenance::build_admin_overview(&state, days).await?;
    Ok(Json(overview))
}

pub(super) async fn admin_probe_now(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<LiveProbeResult>, ApiError> {
    require_admin(&headers, &state.config)?;
    let probe = maintenance::probe_live_dependencies(&state, true).await;
    maintenance::record_health_probe_and_incidents(&state, &probe).await?;
    Ok(Json(probe))
}

#[derive(Debug, Deserialize)]
pub(super) struct SetMaintenanceRequest {
    enabled: bool,
    reason: Option<String>,
}

#[derive(Debug, Serialize)]
pub(super) struct MaintenanceResponse {
    maintenance: MaintenanceStateDto,
    analyzing_active: i64,
    queue_active: i64,
}

async fn build_maintenance_response(
    state: &AppState,
    maintenance: MaintenanceStateDto,
) -> Result<MaintenanceResponse, ApiError> {
    let (analyzing_active,): (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM jobs WHERE deleted_at IS NULL AND status = 'analyzing'",
    )
    .fetch_one(&state.db)
    .await?;
    let queue_active = db::count_active_queue(&state.db).await?;
    Ok(MaintenanceResponse {
        maintenance,
        analyzing_active,
        queue_active,
    })
}

pub(super) async fn admin_get_maintenance(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<MaintenanceResponse>, ApiError> {
    require_admin(&headers, &state.config)?;
    let maintenance = maintenance::get_maintenance_state(&state.db).await?;
    Ok(Json(build_maintenance_response(&state, maintenance).await?))
}

pub(super) async fn admin_set_maintenance(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<SetMaintenanceRequest>,
) -> Result<Json<MaintenanceResponse>, ApiError> {
    require_admin(&headers, &state.config)?;
    let maintenance =
        maintenance::set_maintenance_state(&state.db, req.enabled, req.reason.as_deref()).await?;
    if !req.enabled {
        state.job_notify.notify_one();
    }
    Ok(Json(build_maintenance_response(&state, maintenance).await?))
}

pub(super) async fn admin_get_drift(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<DriftStatusResponseDto>, ApiError> {
    require_admin(&headers, &state.config)?;
    let status = maintenance::get_drift_status(&state.db).await?;
    Ok(Json(status))
}

pub(super) async fn admin_import_drift_reference(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<DriftReferencePayload>,
) -> Result<(StatusCode, Json<DriftReferenceSummary>), ApiError> {
    require_admin(&headers, &state.config)?;
    let saved = maintenance::import_drift_reference(&state.db, payload).await?;
    Ok((StatusCode::CREATED, Json(saved)))
}

#[derive(Debug, Deserialize, Default)]
pub(super) struct EvaluateDriftRequest {
    window_days: Option<i64>,
}

pub(super) async fn admin_evaluate_drift(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<EvaluateDriftRequest>>,
) -> Result<Json<DriftEvaluationDto>, ApiError> {
    require_admin(&headers, &state.config)?;
    let window_days = body
        .and_then(|Json(b)| b.window_days)
        .unwrap_or(30)
        .clamp(1, 365);
    let active_model_sha = state
        .inference
        .health()
        .await
        .ok()
        .and_then(|h| h.model_sha256);
    let eval = maintenance::evaluate_drift_and_store(
        &state.db,
        window_days,
        active_model_sha.as_deref(),
    )
    .await?;
    Ok(Json(eval))
}

#[derive(Debug, Deserialize)]
pub(super) struct AdminFeedbackQuery {
    status: Option<String>,
}

pub(super) async fn admin_list_feedback(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(query): Query<AdminFeedbackQuery>,
) -> Result<Json<AdminFeedbackListDto>, ApiError> {
    require_admin(&headers, &state.config)?;
    let list = maintenance::list_all_feedback_admin(&state.db, query.status.as_deref()).await?;
    Ok(Json(list))
}

pub(super) async fn admin_update_feedback(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(report_id): Path<String>,
    Json(req): Json<UpdateFeedbackRequest>,
) -> Result<Json<FeedbackReportDto>, ApiError> {
    require_admin(&headers, &state.config)?;
    let updated = maintenance::update_feedback_review_admin(&state.db, &report_id, &req).await?;
    Ok(Json(updated))
}

pub(super) async fn admin_record_deployment(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<RecordDeploymentRequest>,
) -> Result<(StatusCode, Json<ModelDeploymentRow>), ApiError> {
    require_admin(&headers, &state.config)?;
    let rec = maintenance::record_model_deployment(&state.db, &req).await?;
    Ok((StatusCode::CREATED, Json(rec)))
}
