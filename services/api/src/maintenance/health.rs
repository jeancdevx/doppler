use std::time::Instant;

use chrono::Utc;
use serde::Serialize;
use sqlx::FromRow;

use crate::config::AppConfig;
use crate::domain::generate_opaque_id;
use crate::error::ApiError;
use crate::inference::InferenceHealth;
use crate::maintenance::auth::get_maintenance_state;
use crate::state::AppState;

#[derive(Debug, Clone, Serialize)]
pub struct ComponentCheckDto {
    pub status: &'static str, // healthy | degraded | unavailable | unknown
    pub latency_ms: Option<f64>,
    pub detail: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct LiveProbeResult {
    pub checked_at: String,
    pub overall_status: &'static str,
    pub ready_for_traffic: bool,
    pub maintenance_mode: bool,
    pub maintenance_reason: Option<String>,
    pub api: ComponentCheckDto,
    pub sqlite: ComponentCheckDto,
    pub inference: ComponentCheckDto,
    pub r2: ComponentCheckDto,
    pub queue_depth: Option<i64>,
    pub analyzing_count: Option<i64>,
    pub sqlite_size_bytes: Option<i64>,
    pub r2_managed_bytes: Option<i64>,
    pub r2_managed_objects: Option<i64>,
    pub inference_detail: Option<InferenceHealth>,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct HealthSampleRow {
    pub id: i64,
    pub checked_at: String,
    pub overall_status: String,
    pub api_status: String,
    pub sqlite_status: String,
    pub sqlite_latency_ms: Option<f64>,
    pub inference_status: String,
    pub inference_latency_ms: Option<f64>,
    pub r2_status: String,
    pub r2_latency_ms: Option<f64>,
    pub queue_depth: Option<i64>,
    pub analyzing_count: Option<i64>,
    pub sqlite_size_bytes: Option<i64>,
    pub r2_managed_bytes: Option<i64>,
    pub r2_managed_objects: Option<i64>,
    pub model_sha256: Option<String>,
    pub contract_version: Option<String>,
    pub maintenance_mode: i64,
    pub detail: Option<String>,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct IncidentRow {
    pub id: String,
    pub component: String,
    pub severity: String,
    pub status: String,
    pub consecutive_failures: i64,
    pub opened_at: String,
    pub resolved_at: Option<String>,
    pub summary: String,
    pub last_error: Option<String>,
}

pub fn measure_sqlite_size_bytes(cfg: &AppConfig) -> Option<i64> {
    let base = cfg.sqlite_file_path()?;
    let mut total: u64 = 0;
    let mut found = false;
    for suffix in ["", "-wal", "-shm"] {
        let candidate = format!("{base}{suffix}");
        if let Ok(meta) = std::fs::metadata(&candidate) {
            total = total.saturating_add(meta.len());
            found = true;
        }
    }
    if found {
        i64::try_from(total).ok()
    } else {
        None
    }
}

/// Comprueba de forma efectiva SQLite, inferencia y R2 sin enmascarar errores como 0 ni "ok".
pub async fn probe_live_dependencies(
    state: &AppState,
    include_r2_usage: bool,
) -> LiveProbeResult {
    let checked_at = Utc::now().to_rfc3339();

    let db_start = Instant::now();
    let db_ping: Result<(i64,), sqlx::Error> =
        sqlx::query_as("SELECT 1").fetch_one(&state.db).await;
    let sqlite_latency_ms = db_start.elapsed().as_secs_f64() * 1000.0;

    let (sqlite_check, queue_depth, analyzing_count, maintenance_mode, maintenance_reason) =
        match db_ping {
            Ok(_) => {
                let queued_res: Result<(i64,), sqlx::Error> = sqlx::query_as(
                    "SELECT COUNT(*) FROM jobs WHERE deleted_at IS NULL AND status IN ('queued', 'analyzing')",
                )
                .fetch_one(&state.db)
                .await;
                let analyzing_res: Result<(i64,), sqlx::Error> = sqlx::query_as(
                    "SELECT COUNT(*) FROM jobs WHERE deleted_at IS NULL AND status = 'analyzing'",
                )
                .fetch_one(&state.db)
                .await;
                let maint = get_maintenance_state(&state.db).await.ok();
                let (m_on, m_reason) = maint
                    .map(|m| (m.enabled, m.reason))
                    .unwrap_or((false, None));

                match (queued_res, analyzing_res) {
                    (Ok((q,)), Ok((a,))) => (
                        ComponentCheckDto {
                            status: "healthy",
                            latency_ms: Some(sqlite_latency_ms),
                            detail: None,
                        },
                        Some(q),
                        Some(a),
                        m_on,
                        m_reason,
                    ),
                    (q_err, a_err) => (
                        ComponentCheckDto {
                            status: "degraded",
                            latency_ms: Some(sqlite_latency_ms),
                            detail: Some(format!(
                                "SELECT 1 respondió, pero falló la lectura de cola: {:?} / {:?}",
                                q_err.err(),
                                a_err.err()
                            )),
                        },
                        None,
                        None,
                        m_on,
                        m_reason,
                    ),
                }
            }
            Err(err) => (
                ComponentCheckDto {
                    status: "unavailable",
                    latency_ms: Some(sqlite_latency_ms),
                    detail: Some(format!("Fallo SELECT 1 en SQLite: {err}")),
                },
                None,
                None,
                false,
                None,
            ),
        };

    let inf_start = Instant::now();
    let (inference_check, inference_detail) = match state.inference.health().await {
        Ok(h) => {
            let lat = inf_start.elapsed().as_secs_f64() * 1000.0;
            let status = if h.ready && h.model_loaded {
                "healthy"
            } else {
                "degraded"
            };
            let detail = if status == "healthy" {
                None
            } else {
                Some("Servicio de inferencia responde, pero el modelo aún no está listo.".to_string())
            };
            (
                ComponentCheckDto {
                    status,
                    latency_ms: Some(lat),
                    detail,
                },
                Some(h),
            )
        }
        Err(err) => (
            ComponentCheckDto {
                status: "unavailable",
                latency_ms: Some(inf_start.elapsed().as_secs_f64() * 1000.0),
                detail: Some(err.to_string()),
            },
            None,
        ),
    };

    let r2_start = Instant::now();
    let (r2_check, r2_managed_bytes, r2_managed_objects) = if !state.config.r2_configured() {
        (
            ComponentCheckDto {
                status: "unavailable",
                latency_ms: None,
                detail: Some("Credenciales R2 no configuradas.".to_string()),
            },
            None,
            None,
        )
    } else {
        match state.r2.check_bucket_reachable().await {
            Ok(()) => {
                let lat = r2_start.elapsed().as_secs_f64() * 1000.0;
                let (bytes, objs) = if include_r2_usage {
                    match state.r2.measure_prefix_usage().await {
                        Ok((b, o)) => (Some(b), Some(o)),
                        Err(_) => (None, None),
                    }
                } else {
                    (None, None)
                };
                (
                    ComponentCheckDto {
                        status: "healthy",
                        latency_ms: Some(lat),
                        detail: None,
                    },
                    bytes,
                    objs,
                )
            }
            Err(err) => (
                ComponentCheckDto {
                    status: "unavailable",
                    latency_ms: Some(r2_start.elapsed().as_secs_f64() * 1000.0),
                    detail: Some(err.to_string()),
                },
                None,
                None,
            ),
        }
    };

    let overall_status = if sqlite_check.status == "unavailable"
        && inference_check.status == "unavailable"
        && r2_check.status == "unavailable"
    {
        "unavailable"
    } else if sqlite_check.status == "healthy"
        && inference_check.status == "healthy"
        && r2_check.status == "healthy"
        && !maintenance_mode
    {
        "healthy"
    } else if sqlite_check.status == "unavailable" {
        "unavailable"
    } else {
        "degraded"
    };

    let ready_for_traffic = overall_status == "healthy" && !maintenance_mode;
    let sqlite_size_bytes = measure_sqlite_size_bytes(&state.config);

    LiveProbeResult {
        checked_at,
        overall_status,
        ready_for_traffic,
        maintenance_mode,
        maintenance_reason,
        api: ComponentCheckDto {
            status: "healthy",
            latency_ms: Some(0.0),
            detail: None,
        },
        sqlite: sqlite_check,
        inference: inference_check,
        r2: r2_check,
        queue_depth,
        analyzing_count,
        sqlite_size_bytes,
        r2_managed_bytes,
        r2_managed_objects,
        inference_detail,
    }
}

pub async fn record_health_probe_and_incidents(
    state: &AppState,
    probe: &LiveProbeResult,
) -> Result<(), ApiError> {
    if probe.sqlite.status == "unavailable" {
        return Ok(());
    }

    let model_sha = probe
        .inference_detail
        .as_ref()
        .and_then(|i| i.model_sha256.as_deref());
    let contract_ver = probe
        .inference_detail
        .as_ref()
        .map(|i| i.contract_version.as_str());

    let detail = if probe.maintenance_mode {
        Some(
            probe
                .maintenance_reason
                .clone()
                .unwrap_or_else(|| "Modo mantenimiento activo".to_string()),
        )
    } else {
        None
    };

    sqlx::query(
        r#"
        INSERT INTO health_samples (
            checked_at, overall_status, api_status, sqlite_status, sqlite_latency_ms,
            inference_status, inference_latency_ms, r2_status, r2_latency_ms,
            queue_depth, analyzing_count, sqlite_size_bytes, r2_managed_bytes,
            r2_managed_objects, model_sha256, contract_version, maintenance_mode, detail
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(&probe.checked_at)
    .bind(probe.overall_status)
    .bind(probe.api.status)
    .bind(probe.sqlite.status)
    .bind(probe.sqlite.latency_ms)
    .bind(probe.inference.status)
    .bind(probe.inference.latency_ms)
    .bind(probe.r2.status)
    .bind(probe.r2.latency_ms)
    .bind(probe.queue_depth)
    .bind(probe.analyzing_count)
    .bind(probe.sqlite_size_bytes)
    .bind(probe.r2_managed_bytes)
    .bind(probe.r2_managed_objects)
    .bind(model_sha)
    .bind(contract_ver)
    .bind(if probe.maintenance_mode { 1_i64 } else { 0_i64 })
    .bind(detail)
    .execute(&state.db)
    .await?;

    let threshold = state.config.incident_failure_threshold.max(1);
    let checks = [
        ("sqlite", probe.sqlite.status, probe.sqlite.detail.as_deref()),
        (
            "inference",
            probe.inference.status,
            probe.inference.detail.as_deref(),
        ),
        ("r2", probe.r2.status, probe.r2.detail.as_deref()),
    ];

    for (component, status, err_detail) in checks {
        update_component_incident(state, component, status, err_detail, threshold).await?;
    }

    Ok(())
}

async fn update_component_incident(
    state: &AppState,
    component: &str,
    status: &str,
    err_detail: Option<&str>,
    threshold: u32,
) -> Result<(), ApiError> {
    let failed = status != "healthy";
    let mut streak = state.failure_streaks.lock().await;
    let count = streak.entry(component.to_string()).or_insert(0);

    if failed {
        *count = count.saturating_add(1);
        let current_count = *count;
        drop(streak);

        if current_count >= threshold {
            let open_row: Option<(String,)> = sqlx::query_as(
                "SELECT id FROM operational_incidents WHERE component = ? AND status = 'open' LIMIT 1",
            )
            .bind(component)
            .fetch_optional(&state.db)
            .await?;

            if let Some((inc_id,)) = open_row {
                sqlx::query(
                    "UPDATE operational_incidents SET consecutive_failures = ?, last_error = ? WHERE id = ?",
                )
                .bind(i64::from(current_count))
                .bind(err_detail)
                .bind(&inc_id)
                .execute(&state.db)
                .await?;
            } else {
                let inc_id = format!("inc_{}", generate_opaque_id(8));
                let now = Utc::now().to_rfc3339();
                let severity = if status == "unavailable" {
                    "critical"
                } else {
                    "warning"
                };
                let summary = format!(
                    "Dependencia '{component}' en estado '{status}' durante {current_count} comprobaciones consecutivas."
                );
                sqlx::query(
                    r#"
                    INSERT INTO operational_incidents (
                        id, component, severity, status, consecutive_failures,
                        opened_at, summary, last_error
                    )
                    VALUES (?, ?, ?, 'open', ?, ?, ?, ?)
                    "#,
                )
                .bind(&inc_id)
                .bind(component)
                .bind(severity)
                .bind(i64::from(current_count))
                .bind(&now)
                .bind(&summary)
                .bind(err_detail)
                .execute(&state.db)
                .await?;
            }
        }
    } else {
        *count = 0;
        drop(streak);

        let now = Utc::now().to_rfc3339();
        sqlx::query(
            r#"
            UPDATE operational_incidents
            SET status = 'resolved', resolved_at = ?
            WHERE component = ? AND status = 'open'
            "#,
        )
        .bind(&now)
        .bind(component)
        .execute(&state.db)
        .await?;
    }

    Ok(())
}
