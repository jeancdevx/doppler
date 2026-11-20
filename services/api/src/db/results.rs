use chrono::Utc;
use sqlx::SqlitePool;

use crate::db::models::{JobRow, WindowRow};
use crate::domain::{
    merge_positive_intervals, AudioInfoDto, JobDetailDto, JobStatus, TimingsDto, WindowDto,
};
use crate::error::ApiError;
use crate::inference::InferenceResult;

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

    let pre_commit_persist_ms = persist_start.elapsed().as_secs_f64() * 1000.0;
    let total_processing_ms_pre =
        queue_wait_ms + processing_started_ms_elapsed + pre_commit_persist_ms;

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
    .bind(if result.audio.downmix_cancellation_candidate {
        1
    } else {
        0
    })
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
    .bind(pre_commit_persist_ms)
    .bind(total_processing_ms_pre)
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

    // Medición efectiva incluyendo el commit de SQLite y registro desacoplado idempotente (sin duplicados)
    let commit_persist_ms = persist_start.elapsed().as_secs_f64() * 1000.0;
    let total_processing_ms = queue_wait_ms + processing_started_ms_elapsed + commit_persist_ms;
    let _ = sqlx::query("UPDATE jobs SET persist_ms = ?, total_processing_ms = ? WHERE id = ?")
        .bind(commit_persist_ms)
        .bind(total_processing_ms)
        .bind(job_id)
        .execute(pool)
        .await;

    crate::maintenance::record_completed_job_telemetry(
        pool,
        job_id,
        result,
        r2_fetch_ms,
        queue_wait_ms,
        commit_persist_ms,
        total_processing_ms,
    )
    .await?;

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
    let _ = crate::maintenance::record_failed_job_telemetry(pool, job_id, error_code).await;
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
