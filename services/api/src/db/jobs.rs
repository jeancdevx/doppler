use chrono::{DateTime, Duration, Utc};
use sqlx::SqlitePool;

use crate::db::models::{ExpiredJobRecord, JobRow};
use crate::domain::{JobStatus, JobSummaryDto};
use crate::error::ApiError;

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
