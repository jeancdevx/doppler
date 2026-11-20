use chrono::{DateTime, Duration, Utc};
use sqlx::{FromRow, SqlitePool};

use crate::domain::{
    merge_positive_intervals, AudioInfoDto, JobDetailDto, JobStatus, JobSummaryDto, TimingsDto,
    WindowDto,
};
use crate::error::ApiError;
use crate::inference::InferenceResult;

#[derive(Debug, Clone, FromRow)]
pub struct JobRow {
    pub id: String,
    pub session_id: String,
    pub filename: String,
    pub content_type: String,
    pub declared_size_bytes: i64,
    pub actual_size_bytes: Option<i64>,
    pub object_key: String,
    pub r2_etag: Option<String>,
    pub status: String,
    pub error_code: Option<String>,
    pub error_message: Option<String>,
    pub audio_sha256: Option<String>,
    pub model_sha256: Option<String>,
    pub contract_version: Option<String>,
    pub contract_sha256: Option<String>,
    pub threshold: Option<f64>,
    pub score_type: Option<String>,
    pub original_sample_rate: Option<i64>,
    pub original_channels: Option<i64>,
    pub prepared_sample_rate: Option<i64>,
    pub prepared_channels: Option<i64>,
    pub duration_seconds: Option<f64>,
    pub prepared_samples: Option<i64>,
    pub peak_before_normalization: Option<f64>,
    pub peak_after_normalization: Option<f64>,
    pub rms_after_normalization: Option<f64>,
    pub downmix_cancellation_candidate: i64,
    pub discarded_tail_samples: Option<i64>,
    pub discarded_tail_seconds: Option<f64>,
    pub window_seconds: Option<f64>,
    pub hop_seconds: Option<f64>,
    pub windows_total: i64,
    pub windows_positive: i64,
    pub short_clip: i64,
    pub short_clip_message: Option<String>,
    pub client_upload_ms: Option<f64>,
    pub queue_wait_ms: Option<f64>,
    pub r2_fetch_ms: Option<f64>,
    pub decode_and_prepare_ms: Option<f64>,
    pub inference_ms: Option<f64>,
    pub persist_ms: Option<f64>,
    pub total_processing_ms: Option<f64>,
    pub run_id: String,
    pub created_at: String,
    pub confirmed_at: Option<String>,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub expires_at: String,
    pub deleted_at: Option<String>,
}

#[derive(Debug, Clone, FromRow)]
pub struct WindowRow {
    pub window_index: i64,
    pub start_seconds: f64,
    pub end_seconds: f64,
    pub score: f64,
    pub label: String,
    pub margin_vs_threshold: f64,
}

#[derive(Debug, Clone, FromRow)]
pub struct ExpiredJobRecord {
    pub id: String,
    pub object_key: String,
}

pub async fn ensure_session(pool: &SqlitePool, session_id: &str) -> Result<(), ApiError> {
    let now = Utc::now().to_rfc3339();
    sqlx::query(
        r#"
        INSERT INTO sessions (id, created_at, last_seen_at)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET last_seen_at = excluded.last_seen_at
        "#,
    )
    .bind(session_id)
    .bind(&now)
    .bind(&now)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn count_recent_session_uploads(
    pool: &SqlitePool,
    session_id: &str,
) -> Result<i64, ApiError> {
    let since = (Utc::now() - Duration::hours(1)).to_rfc3339();
    let (count,): (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM jobs WHERE session_id = ? AND created_at >= ?",
    )
    .bind(session_id)
    .bind(since)
    .fetch_one(pool)
    .await?;
    Ok(count)
}

pub async fn count_active_queue(pool: &SqlitePool) -> Result<i64, ApiError> {
    let (count,): (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM jobs WHERE deleted_at IS NULL AND status IN ('queued', 'analyzing')",
    )
    .fetch_one(pool)
    .await?;
    Ok(count)
}

#[allow(clippy::too_many_arguments)]
pub async fn create_uploading_job(
    pool: &SqlitePool,
    job_id: &str,
    run_id: &str,
    session_id: &str,
    filename: &str,
    content_type: &str,
    declared_size_bytes: i64,
    object_key: &str,
    retention_hours: i64,
) -> Result<String, ApiError> {
    let now = Utc::now();
    let created_at = now.to_rfc3339();
    let expires_at = (now + Duration::hours(retention_hours)).to_rfc3339();

    let mut tx = pool.begin().await?;
    sqlx::query(
        r#"
        INSERT INTO jobs (
            id, session_id, filename, content_type, declared_size_bytes,
            object_key, status, run_id, created_at, expires_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'uploading', ?, ?, ?)
        "#,
    )
    .bind(job_id)
    .bind(session_id)
    .bind(filename)
    .bind(content_type)
    .bind(declared_size_bytes)
    .bind(object_key)
    .bind(run_id)
    .bind(&created_at)
    .bind(&expires_at)
    .execute(&mut *tx)
    .await?;

    sqlx::query(
        "INSERT INTO job_events (job_id, from_status, to_status, detail, created_at) VALUES (?, NULL, 'uploading', 'Presigned PUT emitido', ?)",
    )
    .bind(job_id)
    .bind(&created_at)
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;
    Ok(expires_at)
}

pub async fn get_job_for_session(
    pool: &SqlitePool,
    job_id: &str,
    session_id: &str,
) -> Result<Option<JobRow>, ApiError> {
    let row = sqlx::query_as::<_, JobRow>(
        "SELECT * FROM jobs WHERE id = ? AND session_id = ? AND deleted_at IS NULL",
    )
    .bind(job_id)
    .bind(session_id)
    .fetch_optional(pool)
    .await?;
    Ok(row)
}

pub async fn list_jobs_for_session(
    pool: &SqlitePool,
    session_id: &str,
    limit: i64,
) -> Result<Vec<JobSummaryDto>, ApiError> {
    let rows = sqlx::query_as::<_, JobRow>(
        r#"
        SELECT * FROM jobs
        WHERE session_id = ? AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT ?
        "#,
    )
    .bind(session_id)
    .bind(limit)
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .map(|r| JobSummaryDto {
            job_id: r.id,
            run_id: r.run_id,
            filename: r.filename,
            status: JobStatus::from_db(&r.status),
            declared_size_bytes: r.declared_size_bytes,
            actual_size_bytes: r.actual_size_bytes,
            duration_seconds: r.duration_seconds,
            windows_total: r.windows_total,
            windows_positive: r.windows_positive,
            short_clip: r.short_clip != 0,
            error_code: r.error_code,
            error_message: r.error_message,
            created_at: r.created_at,
            completed_at: r.completed_at,
            expires_at: r.expires_at,
        })
        .collect())
}

pub async fn confirm_upload_and_enqueue(
    pool: &SqlitePool,
    job_id: &str,
    actual_size_bytes: i64,
    etag: Option<&str>,
    client_upload_ms: Option<f64>,
    max_queue_depth: i64,
) -> Result<bool, ApiError> {
    let now = Utc::now().to_rfc3339();
    let mut tx = pool.begin().await?;

    let (active_count,): (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM jobs WHERE deleted_at IS NULL AND status IN ('queued', 'analyzing')",
    )
    .fetch_one(&mut *tx)
    .await?;

    if active_count >= max_queue_depth {
        return Err(ApiError::QueueFull(format!(
            "La cola de análisis alcanzó su capacidad máxima ({max_queue_depth}). Intenta nuevamente en unos segundos."
        )));
    }

    let res = sqlx::query(
        r#"
        UPDATE jobs
        SET status = 'queued',
            actual_size_bytes = ?,
            r2_etag = ?,
            client_upload_ms = COALESCE(?, client_upload_ms),
            confirmed_at = ?
        WHERE id = ? AND status = 'uploading' AND deleted_at IS NULL
        "#,
    )
    .bind(actual_size_bytes)
    .bind(etag)
    .bind(client_upload_ms)
    .bind(&now)
    .bind(job_id)
    .execute(&mut *tx)
    .await?;

    if res.rows_affected() == 1 {
        sqlx::query(
            "INSERT INTO job_events (job_id, from_status, to_status, detail, created_at) VALUES (?, 'uploading', 'queued', ?, ?)",
        )
        .bind(job_id)
        .bind(format!("Objeto verificado en R2 ({actual_size_bytes} bytes)"))
        .bind(&now)
        .execute(&mut *tx)
        .await?;
        tx.commit().await?;
        Ok(true)
    } else {
        tx.rollback().await?;
        Ok(false)
    }
}

pub async fn recover_interrupted_jobs(pool: &SqlitePool) -> Result<u64, ApiError> {
    let now = Utc::now().to_rfc3339();
    let mut tx = pool.begin().await?;
    let interrupted: Vec<(String,)> = sqlx::query_as(
        "SELECT id FROM jobs WHERE status = 'analyzing' AND deleted_at IS NULL",
    )
    .fetch_all(&mut *tx)
    .await?;

    for (job_id,) in &interrupted {
        sqlx::query(
            "UPDATE jobs SET status = 'queued', started_at = NULL WHERE id = ? AND status = 'analyzing'",
        )
        .bind(job_id)
        .execute(&mut *tx)
        .await?;
        sqlx::query(
            "INSERT INTO job_events (job_id, from_status, to_status, detail, created_at) VALUES (?, 'analyzing', 'queued', 'Recuperado tras reinicio del servicio', ?)",
        )
        .bind(job_id)
        .bind(&now)
        .execute(&mut *tx)
        .await?;
    }

    tx.commit().await?;
    Ok(interrupted.len() as u64)
}

pub async fn claim_next_queued_job(pool: &SqlitePool) -> Result<Option<JobRow>, ApiError> {
    let mut tx = pool.begin().await?;
    let candidate = sqlx::query_as::<_, JobRow>(
        r#"
        SELECT * FROM jobs
        WHERE status = 'queued' AND deleted_at IS NULL
        ORDER BY COALESCE(confirmed_at, created_at) ASC
        LIMIT 1
        "#,
    )
    .fetch_optional(&mut *tx)
    .await?;

    let Some(mut job) = candidate else {
        tx.rollback().await?;
        return Ok(None);
    };

    let now_dt = Utc::now();
    let now = now_dt.to_rfc3339();
    let queue_wait_ms = job
        .confirmed_at
        .as_deref()
        .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
        .map(|dt| (now_dt - dt.with_timezone(&Utc)).num_microseconds().unwrap_or(0) as f64 / 1000.0)
        .map(|v| v.max(0.0));

    let res = sqlx::query(
        r#"
        UPDATE jobs
        SET status = 'analyzing',
            started_at = ?,
            queue_wait_ms = ?
        WHERE id = ? AND status = 'queued' AND deleted_at IS NULL
        "#,
    )
    .bind(&now)
    .bind(queue_wait_ms)
    .bind(&job.id)
    .execute(&mut *tx)
    .await?;

    if res.rows_affected() != 1 {
        tx.rollback().await?;
        return Ok(None);
    }

    sqlx::query(
        "INSERT INTO job_events (job_id, from_status, to_status, detail, created_at) VALUES (?, 'queued', 'analyzing', 'Reservado por el despachador', ?)",
    )
    .bind(&job.id)
    .bind(&now)
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;
    job.status = "analyzing".to_string();
    job.started_at = Some(now);
    job.queue_wait_ms = queue_wait_ms;
    Ok(Some(job))
}

#[allow(clippy::too_many_arguments)]
pub async fn complete_job_with_result(
    pool: &SqlitePool,
    job_id: &str,
    result: &InferenceResult,
    r2_fetch_ms: f64,
    queue_wait_ms: f64,
    processing_started_ms_elapsed: f64,
) -> Result<(), ApiError> {
    let persist_start = std::time::Instant::now();
    let now = Utc::now().to_rfc3339();
    let mut tx = pool.begin().await?;

    sqlx::query("DELETE FROM job_windows WHERE job_id = ?")
        .bind(job_id)
        .execute(&mut *tx)
        .await?;

    for win in &result.windows {
        sqlx::query(
            r#"
            INSERT INTO job_windows (
                job_id, window_index, start_seconds, end_seconds,
                score, label, margin_vs_threshold
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            "#,
        )
        .bind(job_id)
        .bind(win.index)
        .bind(win.start_seconds)
        .bind(win.end_seconds)
        .bind(win.score)
        .bind(&win.label)
        .bind(win.margin_vs_threshold)
        .execute(&mut *tx)
        .await?;
    }

    let persist_ms = persist_start.elapsed().as_secs_f64() * 1000.0;
    let total_processing_ms = queue_wait_ms + processing_started_ms_elapsed + persist_ms;

    sqlx::query(
        r#"
        UPDATE jobs
        SET status = 'completed',
            error_code = NULL,
            error_message = NULL,
            audio_sha256 = ?,
            model_sha256 = ?,
            contract_version = ?,
            contract_sha256 = ?,
            threshold = ?,
            score_type = ?,
            original_sample_rate = ?,
            original_channels = ?,
            prepared_sample_rate = ?,
            prepared_channels = ?,
            duration_seconds = ?,
            prepared_samples = ?,
            peak_before_normalization = ?,
            peak_after_normalization = ?,
            rms_after_normalization = ?,
            downmix_cancellation_candidate = ?,
            discarded_tail_samples = ?,
            discarded_tail_seconds = ?,
            window_seconds = ?,
            hop_seconds = ?,
            windows_total = ?,
            windows_positive = ?,
            short_clip = ?,
            short_clip_message = ?,
            r2_fetch_ms = ?,
            decode_and_prepare_ms = ?,
            inference_ms = ?,
            persist_ms = ?,
            total_processing_ms = ?,
            completed_at = ?
        WHERE id = ? AND deleted_at IS NULL
        "#,
    )
    .bind(&result.audio_sha256)
    .bind(&result.model_sha256)
    .bind(&result.contract_version)
    .bind(&result.contract_sha256)
    .bind(result.threshold)
    .bind(&result.score_type)
    .bind(result.audio.original_sample_rate)
    .bind(result.audio.original_channels)
    .bind(result.audio.prepared_sample_rate)
    .bind(result.audio.prepared_channels)
    .bind(result.audio.duration_seconds)
    .bind(result.audio.prepared_samples)
    .bind(result.audio.peak_before_normalization)
    .bind(result.audio.peak_after_normalization)
    .bind(result.audio.rms_after_normalization)
    .bind(if result.audio.downmix_cancellation_candidate { 1 } else { 0 })
    .bind(result.audio.discarded_tail_samples)
    .bind(result.audio.discarded_tail_seconds)
    .bind(result.audio.window_seconds)
    .bind(result.audio.hop_seconds)
    .bind(result.windows_total)
    .bind(result.windows_positive)
    .bind(if result.short_clip { 1 } else { 0 })
    .bind(&result.short_clip_message)
    .bind(r2_fetch_ms)
    .bind(result.timings.decode_and_prepare_ms)
    .bind(result.timings.inference_ms)
    .bind(persist_ms)
    .bind(total_processing_ms)
    .bind(&now)
    .bind(job_id)
    .execute(&mut *tx)
    .await?;

    sqlx::query(
        "INSERT INTO job_events (job_id, from_status, to_status, detail, created_at) VALUES (?, 'analyzing', 'completed', ?, ?)",
    )
    .bind(job_id)
    .bind(format!(
        "Completado: {} ventanas ({} positivas)",
        result.windows_total, result.windows_positive
    ))
    .bind(&now)
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;
    Ok(())
}

pub async fn mark_job_failed(
    pool: &SqlitePool,
    job_id: &str,
    from_status: &str,
    error_code: &str,
    error_message: &str,
) -> Result<(), ApiError> {
    let now = Utc::now().to_rfc3339();
    let mut tx = pool.begin().await?;
    sqlx::query(
        r#"
        UPDATE jobs
        SET status = 'failed',
            error_code = ?,
            error_message = ?,
            completed_at = ?
        WHERE id = ? AND deleted_at IS NULL
        "#,
    )
    .bind(error_code)
    .bind(error_message)
    .bind(&now)
    .bind(job_id)
    .execute(&mut *tx)
    .await?;

    sqlx::query(
        "INSERT INTO job_events (job_id, from_status, to_status, detail, created_at) VALUES (?, ?, 'failed', ?, ?)",
    )
    .bind(job_id)
    .bind(from_status)
    .bind(format!("{error_code}: {error_message}"))
    .bind(&now)
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;
    Ok(())
}

pub async fn build_job_detail(
    pool: &SqlitePool,
    job: JobRow,
) -> Result<JobDetailDto, ApiError> {
    let window_rows = sqlx::query_as::<_, WindowRow>(
        "SELECT window_index, start_seconds, end_seconds, score, label, margin_vs_threshold FROM job_windows WHERE job_id = ? ORDER BY window_index ASC",
    )
    .bind(&job.id)
    .fetch_all(pool)
    .await?;

    let windows: Vec<WindowDto> = window_rows
        .into_iter()
        .map(|w| WindowDto {
            index: w.window_index,
            start_seconds: w.start_seconds,
            end_seconds: w.end_seconds,
            score: w.score,
            label: w.label,
            margin_vs_threshold: w.margin_vs_threshold,
        })
        .collect();

    let (merged_positive_intervals, positive_coverage_seconds) =
        merge_positive_intervals(&windows);

    let status = JobStatus::from_db(&job.status);
    let queue_position = if status == JobStatus::Queued {
        let pivot = job.confirmed_at.as_deref().unwrap_or(&job.created_at);
        let (ahead,): (i64,) = sqlx::query_as(
            "SELECT COUNT(*) FROM jobs WHERE deleted_at IS NULL AND status IN ('queued', 'analyzing') AND COALESCE(confirmed_at, created_at) <= ?",
        )
        .bind(pivot)
        .fetch_one(pool)
        .await?;
        Some(ahead.max(1))
    } else {
        None
    };

    let audio = match (
        job.original_sample_rate,
        job.original_channels,
        job.prepared_sample_rate,
        job.prepared_channels,
        job.duration_seconds,
        job.prepared_samples,
    ) {
        (Some(osr), Some(och), Some(psr), Some(pch), Some(dur), Some(psamp)) => {
            Some(AudioInfoDto {
                original_sample_rate: osr,
                original_channels: och,
                prepared_sample_rate: psr,
                prepared_channels: pch,
                duration_seconds: dur,
                prepared_samples: psamp,
                peak_before_normalization: job.peak_before_normalization.unwrap_or(0.0),
                peak_after_normalization: job.peak_after_normalization.unwrap_or(0.0),
                rms_after_normalization: job.rms_after_normalization.unwrap_or(0.0),
                downmix_cancellation_candidate: job.downmix_cancellation_candidate != 0,
                discarded_tail_samples: job.discarded_tail_samples.unwrap_or(0),
                discarded_tail_seconds: job.discarded_tail_seconds.unwrap_or(0.0),
                window_seconds: job.window_seconds.unwrap_or(3.0),
                hop_seconds: job.hop_seconds.unwrap_or(1.5),
            })
        }
        _ => None,
    };

    Ok(JobDetailDto {
        job_id: job.id,
        run_id: job.run_id,
        filename: job.filename,
        status,
        queue_position,
        declared_size_bytes: job.declared_size_bytes,
        actual_size_bytes: job.actual_size_bytes,
        error_code: job.error_code,
        error_message: job.error_message,
        audio_sha256: job.audio_sha256,
        model_sha256: job.model_sha256,
        contract_version: job.contract_version,
        contract_sha256: job.contract_sha256,
        threshold: job.threshold,
        score_type: job.score_type,
        audio,
        windows_total: job.windows_total,
        windows_positive: job.windows_positive,
        positive_coverage_seconds,
        positive_coverage_note: "Los intervalos unidos se derivan de ventanas solapadas de 3,0 s (salto 1,5 s); no constituyen localización exacta del inicio ni fin de la sirena.",
        merged_positive_intervals,
        windows,
        short_clip: job.short_clip != 0,
        short_clip_message: job.short_clip_message,
        timings: TimingsDto {
            client_upload_ms: job.client_upload_ms,
            queue_wait_ms: job.queue_wait_ms,
            r2_fetch_ms: job.r2_fetch_ms,
            decode_and_prepare_ms: job.decode_and_prepare_ms,
            inference_ms: job.inference_ms,
            persist_ms: job.persist_ms,
            total_processing_ms: job.total_processing_ms,
        },
        created_at: job.created_at,
        confirmed_at: job.confirmed_at,
        started_at: job.started_at,
        completed_at: job.completed_at,
        expires_at: job.expires_at,
    })
}

pub async fn hard_delete_job(pool: &SqlitePool, job_id: &str) -> Result<(), ApiError> {
    sqlx::query("DELETE FROM jobs WHERE id = ?")
        .bind(job_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn find_expired_or_abandoned_jobs(
    pool: &SqlitePool,
    abandoned_upload_minutes: i64,
) -> Result<Vec<ExpiredJobRecord>, ApiError> {
    let now = Utc::now();
    let now_str = now.to_rfc3339();
    let abandoned_cutoff = (now - Duration::minutes(abandoned_upload_minutes)).to_rfc3339();

    let rows = sqlx::query_as::<_, ExpiredJobRecord>(
        r#"
        SELECT id, object_key FROM jobs
        WHERE expires_at <= ?
           OR (status = 'uploading' AND created_at <= ?)
        LIMIT 100
        "#,
    )
    .bind(now_str)
    .bind(abandoned_cutoff)
    .fetch_all(pool)
    .await?;
    Ok(rows)
}
