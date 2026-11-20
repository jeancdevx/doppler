use std::collections::BTreeMap;
use std::time::Instant;

use chrono::{Duration, Utc};
use serde::Serialize;
use sqlx::{FromRow, SqlitePool};

use crate::error::ApiError;
use crate::inference::InferenceResult;
use crate::maintenance::deployments::{list_recent_deployments, ModelDeploymentRow};
use crate::maintenance::health::{
    probe_live_dependencies, HealthSampleRow, IncidentRow, LiveProbeResult,
};
use crate::state::AppState;

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct RetentionRunRow {
    pub id: i64,
    pub ran_at: String,
    pub scope: String,
    pub jobs_deleted: i64,
    pub r2_objects_deleted: i64,
    pub r2_errors: i64,
    pub history_rows_deleted: i64,
    pub duration_ms: f64,
    pub status: String,
    pub detail: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct LatencySummaryDto {
    pub n: usize,
    pub p50_ms: Option<f64>,
    pub p95_ms: Option<f64>,
    pub mean_ms: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DurationBucketLatencyDto {
    pub bucket: String,
    pub n: usize,
    pub r2_fetch_p50_ms: Option<f64>,
    pub decode_prepare_p50_ms: Option<f64>,
    pub inference_p50_ms: Option<f64>,
    pub inference_p95_ms: Option<f64>,
    pub total_processing_p50_ms: Option<f64>,
    pub total_processing_p95_ms: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct JobCountersDto {
    pub window_days: i64,
    pub total_recorded: i64,
    pub completed: i64,
    pub user_validation_errors: i64,
    pub internal_errors: i64,
    pub short_clips: i64,
    pub active_jobs_in_24h_table: i64,
    pub user_deleted_in_history: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct StorageMetricsDto {
    pub sqlite_size_bytes: Option<i64>,
    pub sqlite_measurement_method: &'static str,
    pub r2_managed_bytes: Option<i64>,
    pub r2_managed_objects: Option<i64>,
    pub r2_measurement_method: &'static str,
}

#[derive(Debug, Clone, Serialize)]
pub struct LatencyStagesDto {
    pub queue_wait: LatencySummaryDto,
    pub r2_fetch: LatencySummaryDto,
    pub decode_and_prepare: LatencySummaryDto,
    pub inference: LatencySummaryDto,
    pub persist: LatencySummaryDto,
    pub total_processing: LatencySummaryDto,
}

#[derive(Debug, Clone, Serialize)]
pub struct MonitoringConfigViewDto {
    pub health_check_interval_seconds: u64,
    pub incident_failure_threshold: u32,
    pub job_retention_hours: i64,
    pub history_retention_days: i64,
    pub max_concurrent_inference: usize,
    pub max_queue_depth: i64,
    pub telemetry_redact_on_user_delete: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct AdminOverviewDto {
    pub generated_at: String,
    pub live: LiveProbeResult,
    pub counters: JobCountersDto,
    pub latencies: LatencyStagesDto,
    pub latency_by_duration_bucket: Vec<DurationBucketLatencyDto>,
    pub timing_boundary_note: &'static str,
    pub storage: StorageMetricsDto,
    pub monitoring_config: MonitoringConfigViewDto,
    pub recent_health_samples: Vec<HealthSampleRow>,
    pub incidents: Vec<IncidentRow>,
    pub retention_runs: Vec<RetentionRunRow>,
    pub model_deployments: Vec<ModelDeploymentRow>,
}

#[derive(Debug, Clone, FromRow)]
struct TelemetryLatencyRow {
    outcome: String,
    short_clip: i64,
    user_deleted: i64,
    duration_seconds: Option<f64>,
    queue_wait_ms: Option<f64>,
    r2_fetch_ms: Option<f64>,
    decode_and_prepare_ms: Option<f64>,
    inference_ms: Option<f64>,
    persist_ms: Option<f64>,
    total_processing_ms: Option<f64>,
}

pub fn classify_error_outcome(error_code: &str) -> &'static str {
    match error_code {
        "decode_error" | "invalid_format" | "duration_exceeded" | "validation_error"
        | "limit_exceeded" | "upload_error" => "user_validation_error",
        _ => "internal_error",
    }
}

pub fn summarize_f64(values: &[f64]) -> (Option<f64>, Option<f64>, Option<f64>, Option<f64>) {
    let finite: Vec<f64> = values.iter().copied().filter(|v| v.is_finite()).collect();
    if finite.is_empty() {
        return (None, None, None, None);
    }
    let n = finite.len() as f64;
    let mean = finite.iter().sum::<f64>() / n;
    let mut min_v = f64::INFINITY;
    let mut max_v = f64::NEG_INFINITY;
    let mut var_sum = 0.0;
    for v in &finite {
        if *v < min_v {
            min_v = *v;
        }
        if *v > max_v {
            max_v = *v;
        }
        let d = *v - mean;
        var_sum += d * d;
    }
    (Some(mean), Some(max_v), Some(min_v), Some((var_sum / n).sqrt()))
}

pub fn percentile(values: &[f64], pct: f64) -> Option<f64> {
    let mut sorted: Vec<f64> = values.iter().copied().filter(|v| v.is_finite()).collect();
    if sorted.is_empty() {
        return None;
    }
    sorted.sort_by(f64::total_cmp);
    if sorted.len() == 1 {
        return Some(sorted[0]);
    }
    let rank = (pct / 100.0) * ((sorted.len() - 1) as f64);
    let lo = rank.floor() as usize;
    let hi = rank.ceil() as usize;
    let frac = rank - (lo as f64);
    Some(sorted[lo] + frac * (sorted[hi] - sorted[lo]))
}

#[allow(clippy::too_many_arguments)]
pub async fn record_completed_job_telemetry(
    pool: &SqlitePool,
    job_id: &str,
    result: &InferenceResult,
    r2_fetch_ms: f64,
    queue_wait_ms: f64,
    persist_ms: f64,
    total_processing_ms: f64,
) -> Result<(), ApiError> {
    let now = Utc::now().to_rfc3339();
    let scores: Vec<f64> = result.windows.iter().map(|w| w.score).collect();
    let (score_mean, score_max, score_min, score_std) = summarize_f64(&scores);
    let positive_ratio = if result.windows_total > 0 {
        Some(result.windows_positive as f64 / result.windows_total as f64)
    } else {
        None
    };
    let obs = result.audio.observational.as_ref();

    sqlx::query(
        r#"
        INSERT OR IGNORE INTO job_telemetry_history (
            job_id, recorded_at, outcome, error_code,
            model_sha256, contract_version, contract_sha256, threshold, extraction_version,
            original_sample_rate, original_channels, duration_seconds,
            peak_before_normalization, rms_before_normalization, rms_after_normalization,
            silence_ratio, clipping_ratio, downmix_cancellation_candidate,
            short_clip, discarded_tail_seconds, logmel_mean, logmel_std, spectral_centroid_hz,
            windows_total, windows_positive, positive_window_ratio,
            score_mean, score_max, score_min, score_std,
            r2_fetch_ms, queue_wait_ms, decode_and_prepare_ms, inference_ms, persist_ms, total_processing_ms
        )
        VALUES (
            ?, ?, 'completed', NULL,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?
        )
        "#,
    )
    .bind(job_id)
    .bind(&now)
    .bind(&result.model_sha256)
    .bind(&result.contract_version)
    .bind(&result.contract_sha256)
    .bind(result.threshold)
    .bind(obs.map(|o| o.extraction_version.as_str()).unwrap_or("obs_v1"))
    .bind(result.audio.original_sample_rate)
    .bind(result.audio.original_channels)
    .bind(result.audio.duration_seconds)
    .bind(result.audio.peak_before_normalization)
    .bind(obs.map(|o| o.rms_before_normalization))
    .bind(result.audio.rms_after_normalization)
    .bind(obs.map(|o| o.silence_ratio))
    .bind(obs.map(|o| o.clipping_ratio))
    .bind(if result.audio.downmix_cancellation_candidate { 1_i64 } else { 0_i64 })
    .bind(if result.short_clip { 1_i64 } else { 0_i64 })
    .bind(result.audio.discarded_tail_seconds)
    .bind(obs.and_then(|o| o.logmel_mean))
    .bind(obs.and_then(|o| o.logmel_std))
    .bind(obs.and_then(|o| o.spectral_centroid_hz))
    .bind(result.windows_total)
    .bind(result.windows_positive)
    .bind(positive_ratio)
    .bind(score_mean)
    .bind(score_max)
    .bind(score_min)
    .bind(score_std)
    .bind(r2_fetch_ms)
    .bind(queue_wait_ms)
    .bind(result.timings.decode_and_prepare_ms)
    .bind(result.timings.inference_ms)
    .bind(persist_ms)
    .bind(total_processing_ms)
    .execute(pool)
    .await?;

    Ok(())
}

pub async fn record_failed_job_telemetry(
    pool: &SqlitePool,
    job_id: &str,
    error_code: &str,
) -> Result<(), ApiError> {
    let now = Utc::now().to_rfc3339();
    let outcome = classify_error_outcome(error_code);
    sqlx::query(
        "INSERT OR IGNORE INTO job_telemetry_history (job_id, recorded_at, outcome, error_code) VALUES (?, ?, ?, ?)",
    )
    .bind(job_id)
    .bind(&now)
    .bind(outcome)
    .bind(error_code)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn mark_telemetry_user_deleted(
    pool: &SqlitePool,
    job_id: &str,
    redact_detailed: bool,
) -> Result<(), ApiError> {
    if redact_detailed {
        sqlx::query(
            r#"
            UPDATE job_telemetry_history
            SET user_deleted = 1, logmel_mean = NULL, logmel_std = NULL, spectral_centroid_hz = NULL
            WHERE job_id = ?
            "#,
        )
        .bind(job_id)
        .execute(pool)
        .await?;
    } else {
        sqlx::query("UPDATE job_telemetry_history SET user_deleted = 1 WHERE job_id = ?")
            .bind(job_id)
            .execute(pool)
            .await?;
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
pub async fn record_retention_run(
    pool: &SqlitePool,
    scope: &str,
    jobs_deleted: i64,
    r2_objects_deleted: i64,
    r2_errors: i64,
    history_rows_deleted: i64,
    duration_ms: f64,
    status: &str,
    detail: Option<&str>,
) -> Result<(), ApiError> {
    let now = Utc::now().to_rfc3339();
    sqlx::query(
        r#"
        INSERT INTO retention_runs (
            ran_at, scope, jobs_deleted, r2_objects_deleted, r2_errors,
            history_rows_deleted, duration_ms, status, detail
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(&now)
    .bind(scope)
    .bind(jobs_deleted)
    .bind(r2_objects_deleted)
    .bind(r2_errors)
    .bind(history_rows_deleted)
    .bind(duration_ms)
    .bind(status)
    .bind(detail)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn purge_expired_maintenance_history(
    pool: &SqlitePool,
    retention_days: i64,
) -> Result<i64, ApiError> {
    let start = Instant::now();
    let cutoff = (Utc::now() - Duration::days(retention_days.max(1))).to_rfc3339();

    let h1 = sqlx::query("DELETE FROM health_samples WHERE checked_at < ?")
        .bind(&cutoff)
        .execute(pool)
        .await?
        .rows_affected();
    let h2 = sqlx::query("DELETE FROM job_telemetry_history WHERE recorded_at < ?")
        .bind(&cutoff)
        .execute(pool)
        .await?
        .rows_affected();
    let h3 = sqlx::query("DELETE FROM drift_evaluations WHERE evaluated_at < ?")
        .bind(&cutoff)
        .execute(pool)
        .await?
        .rows_affected();
    let h4 = sqlx::query(
        "DELETE FROM operational_incidents WHERE status = 'resolved' AND resolved_at IS NOT NULL AND resolved_at < ?",
    )
    .bind(&cutoff)
    .execute(pool)
    .await?
    .rows_affected();
    let h5 = sqlx::query("DELETE FROM retention_runs WHERE ran_at < ?")
        .bind(&cutoff)
        .execute(pool)
        .await?
        .rows_affected();

    let total_deleted = (h1 + h2 + h3 + h4 + h5) as i64;
    let duration_ms = start.elapsed().as_secs_f64() * 1000.0;
    record_retention_run(
        pool,
        "maintenance_history",
        0,
        0,
        0,
        total_deleted,
        duration_ms,
        "ok",
        Some(&format!(
            "Corte {retention_days} días (health={h1}, telemetry={h2}, drift_eval={h3}, incidents={h4}, retention={h5}); referencias congeladas conservadas."
        )),
    )
    .await?;

    Ok(total_deleted)
}

pub async fn build_admin_overview(
    state: &AppState,
    window_days: i64,
) -> Result<AdminOverviewDto, ApiError> {
    let live = probe_live_dependencies(state, true).await;
    let cutoff = (Utc::now() - Duration::days(window_days.max(1))).to_rfc3339();

    let rows = sqlx::query_as::<_, TelemetryLatencyRow>(
        r#"
        SELECT outcome, short_clip, user_deleted, duration_seconds,
               queue_wait_ms, r2_fetch_ms, decode_and_prepare_ms,
               inference_ms, persist_ms, total_processing_ms
        FROM job_telemetry_history
        WHERE recorded_at >= ?
        ORDER BY recorded_at DESC
        "#,
    )
    .bind(&cutoff)
    .fetch_all(&state.db)
    .await?;

    let (active_jobs_24h,): (i64,) =
        sqlx::query_as("SELECT COUNT(*) FROM jobs WHERE deleted_at IS NULL")
            .fetch_one(&state.db)
            .await?;

    let (mut completed, mut user_errors, mut internal_errors, mut short_clips, mut user_deleted) =
        (0_i64, 0_i64, 0_i64, 0_i64, 0_i64);
    let (mut q_vals, mut r2_vals, mut prep_vals, mut inf_vals, mut pers_vals, mut tot_vals) = (
        Vec::new(),
        Vec::new(),
        Vec::new(),
        Vec::new(),
        Vec::new(),
        Vec::new(),
    );
    let mut buckets: BTreeMap<&'static str, Vec<&TelemetryLatencyRow>> = BTreeMap::new();

    for r in &rows {
        if r.user_deleted != 0 {
            user_deleted += 1;
        }
        match r.outcome.as_str() {
            "completed" => {
                completed += 1;
                if r.short_clip != 0 {
                    short_clips += 1;
                }
                if let Some(v) = r.queue_wait_ms { q_vals.push(v); }
                if let Some(v) = r.r2_fetch_ms { r2_vals.push(v); }
                if let Some(v) = r.decode_and_prepare_ms { prep_vals.push(v); }
                if let Some(v) = r.inference_ms { inf_vals.push(v); }
                if let Some(v) = r.persist_ms { pers_vals.push(v); }
                if let Some(v) = r.total_processing_ms { tot_vals.push(v); }
                buckets.entry(duration_bucket_name(r.duration_seconds)).or_default().push(r);
            }
            "user_validation_error" => user_errors += 1,
            _ => internal_errors += 1,
        }
    }

    let bucket_stats = [
        "01_menor_3s",
        "02_3s_a_6s",
        "03_6s_a_15s",
        "04_15s_a_30s",
        "05_30s_a_120s",
    ]
    .into_iter()
    .filter_map(|key| {
        let items = buckets.get(key)?;
        let r2_b: Vec<f64> = items.iter().filter_map(|x| x.r2_fetch_ms).collect();
        let pr_b: Vec<f64> = items.iter().filter_map(|x| x.decode_and_prepare_ms).collect();
        let in_b: Vec<f64> = items.iter().filter_map(|x| x.inference_ms).collect();
        let to_b: Vec<f64> = items.iter().filter_map(|x| x.total_processing_ms).collect();
        Some(DurationBucketLatencyDto {
            bucket: key.to_string(),
            n: items.len(),
            r2_fetch_p50_ms: percentile(&r2_b, 50.0),
            decode_prepare_p50_ms: percentile(&pr_b, 50.0),
            inference_p50_ms: percentile(&in_b, 50.0),
            inference_p95_ms: percentile(&in_b, 95.0),
            total_processing_p50_ms: percentile(&to_b, 50.0),
            total_processing_p95_ms: percentile(&to_b, 95.0),
        })
    })
    .collect();

    let recent_health_samples = sqlx::query_as::<_, HealthSampleRow>(
        "SELECT * FROM health_samples ORDER BY id DESC LIMIT 30",
    )
    .fetch_all(&state.db)
    .await?;

    let incidents = sqlx::query_as::<_, IncidentRow>(
        "SELECT * FROM operational_incidents ORDER BY opened_at DESC LIMIT 30",
    )
    .fetch_all(&state.db)
    .await?;

    let retention_runs = sqlx::query_as::<_, RetentionRunRow>(
        "SELECT * FROM retention_runs ORDER BY id DESC LIMIT 20",
    )
    .fetch_all(&state.db)
    .await?;

    let model_deployments = list_recent_deployments(&state.db, 20).await?;

    Ok(AdminOverviewDto {
        generated_at: Utc::now().to_rfc3339(),
        storage: StorageMetricsDto {
            sqlite_size_bytes: live.sqlite_size_bytes,
            sqlite_measurement_method: "Suma de st_size de archivos SQLite (.db + -wal + -shm) en el volumen montado /data.",
            r2_managed_bytes: live.r2_managed_bytes,
            r2_managed_objects: live.r2_managed_objects,
            r2_measurement_method: "Suma de Size vía ListObjectsV2 acotado estrictamente al prefijo configurado R2_PREFIX.",
        },
        live,
        counters: JobCountersDto {
            window_days,
            total_recorded: rows.len() as i64,
            completed,
            user_validation_errors: user_errors,
            internal_errors,
            short_clips,
            active_jobs_in_24h_table: active_jobs_24h,
            user_deleted_in_history: user_deleted,
        },
        latencies: LatencyStagesDto {
            queue_wait: latency_summary(&q_vals),
            r2_fetch: latency_summary(&r2_vals),
            decode_and_prepare: latency_summary(&prep_vals),
            inference: latency_summary(&inf_vals),
            persist: latency_summary(&pers_vals),
            total_processing: latency_summary(&tot_vals),
        },
        latency_by_duration_bucket: bucket_stats,
        timing_boundary_note: "queue_wait: confirmación→reserva worker; r2_fetch: descarga acotada Rust←R2; decode_and_prepare: decodificación+resample+Log-Mel Python; inference: forward ResNet18 CPU; persist: transacción SQLite incluyendo commit; total_processing: tiempo servidor (no incluye subida PUT del navegador).",
        monitoring_config: MonitoringConfigViewDto {
            health_check_interval_seconds: state.config.health_check_interval_seconds,
            incident_failure_threshold: state.config.incident_failure_threshold,
            job_retention_hours: state.config.retention_hours,
            history_retention_days: state.config.history_retention_days,
            max_concurrent_inference: state.config.max_concurrent_inference,
            max_queue_depth: state.config.max_queue_depth,
            telemetry_redact_on_user_delete: state.config.telemetry_redact_on_user_delete,
        },
        recent_health_samples,
        incidents,
        retention_runs,
        model_deployments,
    })
}

fn duration_bucket_name(dur: Option<f64>) -> &'static str {
    match dur {
        Some(d) if d < 3.0 => "01_menor_3s",
        Some(d) if d <= 6.5 => "02_3s_a_6s",
        Some(d) if d <= 15.5 => "03_6s_a_15s",
        Some(d) if d <= 30.5 => "04_15s_a_30s",
        _ => "05_30s_a_120s",
    }
}

fn latency_summary(values: &[f64]) -> LatencySummaryDto {
    let finite: Vec<f64> = values.iter().copied().filter(|v| v.is_finite()).collect();
    let mean = if finite.is_empty() {
        None
    } else {
        Some(finite.iter().sum::<f64>() / (finite.len() as f64))
    };
    LatencySummaryDto {
        n: finite.len(),
        p50_ms: percentile(&finite, 50.0),
        p95_ms: percentile(&finite, 95.0),
        mean_ms: mean,
    }
}
