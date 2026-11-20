use chrono::{Duration, Utc};
use sqlx::SqlitePool;

use crate::error::ApiError;

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
