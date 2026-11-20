use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Json;
use axum_extra::extract::cookie::CookieJar;

use crate::error::ApiError;
use crate::maintenance::{self, CreateFeedbackRequest, FeedbackReportDto};
use crate::routes::auth::require_session;
use crate::state::AppState;

pub(super) async fn create_job_feedback(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
    Json(req): Json<CreateFeedbackRequest>,
) -> Result<(StatusCode, Json<FeedbackReportDto>), ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let created = maintenance::create_feedback_report(
        &state.db,
        &session_id,
        &job_id,
        &req,
        state.config.rate_limit_feedback_per_hour,
    )
    .await?;
    Ok((StatusCode::CREATED, Json(created)))
}

pub(super) async fn list_job_feedback(
    State(state): State<AppState>,
    jar: CookieJar,
    Path(job_id): Path<String>,
) -> Result<Json<Vec<FeedbackReportDto>>, ApiError> {
    let session_id = require_session(&jar, &state).await?;
    let items = maintenance::list_feedback_for_session_job(&state.db, &session_id, &job_id).await?;
    Ok(Json(items))
}
