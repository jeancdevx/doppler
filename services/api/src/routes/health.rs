use axum::extract::State;
use axum::http::StatusCode;
use axum::Json;
use serde::Serialize;

use crate::config::AppConfig;
use crate::domain::LimitsInfo;
use crate::error::ApiError;
use crate::inference::InferenceHealth;
use crate::maintenance::{self, ComponentCheckDto, LiveProbeResult};
use crate::routes::auth::limits_from_config;
use crate::state::AppState;

#[derive(Debug, Serialize)]
pub(super) struct HealthResponse {
    status: &'static str,
    overall_status: &'static str,
    ready: bool,
    maintenance_mode: bool,
    maintenance_reason: Option<String>,
    api: &'static str,
    database: &'static str,
    r2_configured: bool,
    r2_reachable: bool,
    queue_active: Option<i64>,
    analyzing_active: Option<i64>,
    max_queue_depth: i64,
    max_concurrent_inference: usize,
    components: HealthComponents,
    limits: LimitsInfo,
    inference: Option<InferenceHealth>,
}

#[derive(Debug, Serialize)]
struct HealthComponents {
    api: ComponentCheckDto,
    sqlite: ComponentCheckDto,
    inference: ComponentCheckDto,
    r2: ComponentCheckDto,
}

fn build_health_payload(probe: LiveProbeResult, cfg: &AppConfig) -> HealthResponse {
    // Mantiene retrocompatibilidad del campo `status` ("ok" | "degraded")
    // y añade `overall_status` detallado ("healthy" | "degraded" | "unavailable" | "unknown")
    let legacy_status = if probe.ready_for_traffic {
        "ok"
    } else {
        "degraded"
    };
    let legacy_db = if probe.sqlite.status == "healthy" {
        "ok"
    } else {
        probe.sqlite.status
    };

    HealthResponse {
        status: legacy_status,
        overall_status: probe.overall_status,
        ready: probe.ready_for_traffic,
        maintenance_mode: probe.maintenance_mode,
        maintenance_reason: probe.maintenance_reason,
        api: "ok",
        database: legacy_db,
        r2_configured: cfg.r2_configured(),
        r2_reachable: probe.r2.status == "healthy",
        queue_active: probe.queue_depth,
        analyzing_active: probe.analyzing_count,
        max_queue_depth: cfg.max_queue_depth,
        max_concurrent_inference: cfg.max_concurrent_inference,
        components: HealthComponents {
            api: probe.api,
            sqlite: probe.sqlite,
            inference: probe.inference,
            r2: probe.r2,
        },
        limits: limits_from_config(cfg),
        inference: probe.inference_detail,
    }
}

pub(super) async fn health(State(state): State<AppState>) -> Result<Json<HealthResponse>, ApiError> {
    let probe = maintenance::probe_live_dependencies(&state, false).await;
    Ok(Json(build_health_payload(probe, &state.config)))
}

/// Comprobación estricta de readiness con semántica HTTP 200 vs 503.
pub(super) async fn ready(State(state): State<AppState>) -> (StatusCode, Json<HealthResponse>) {
    let probe = maintenance::probe_live_dependencies(&state, false).await;
    let code = if probe.ready_for_traffic {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };
    (code, Json(build_health_payload(probe, &state.config)))
}
