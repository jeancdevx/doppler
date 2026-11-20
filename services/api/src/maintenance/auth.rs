use chrono::Utc;
use serde::Serialize;
use sqlx::{FromRow, SqlitePool};
use subtle::ConstantTimeEq;

use crate::error::ApiError;

#[derive(Debug, Clone, Serialize)]
pub struct MaintenanceStateDto {
    pub enabled: bool,
    pub reason: Option<String>,
    pub updated_at: String,
}

#[derive(Debug, Clone, FromRow)]
struct MaintenanceStateRow {
    enabled: i64,
    reason: Option<String>,
    updated_at: String,
}

pub fn verify_admin_token(provided: Option<&str>, configured: Option<&str>) -> Result<(), ApiError> {
    let Some(expected) = configured else {
        return Err(ApiError::Config(
            "ADMIN_API_TOKEN no está configurado en el servidor.".to_string(),
        ));
    };
    let Some(token) = provided.map(str::trim).filter(|s| !s.is_empty()) else {
        return Err(ApiError::Unauthorized(
            "Se requiere credencial administrativa válida en el encabezado X-Admin-Token."
                .to_string(),
        ));
    };
    let a = token.as_bytes();
    let b = expected.as_bytes();
    if a.len() == b.len() && bool::from(a.ct_eq(b)) {
        Ok(())
    } else {
        Err(ApiError::Unauthorized(
            "Credencial administrativa inválida.".to_string(),
        ))
    }
}

pub async fn get_maintenance_state(pool: &SqlitePool) -> Result<MaintenanceStateDto, ApiError> {
    let row = sqlx::query_as::<_, MaintenanceStateRow>(
        "SELECT enabled, reason, updated_at FROM maintenance_state WHERE id = 1",
    )
    .fetch_optional(pool)
    .await?;

    Ok(match row {
        Some(r) => MaintenanceStateDto {
            enabled: r.enabled != 0,
            reason: r.reason,
            updated_at: r.updated_at,
        },
        None => MaintenanceStateDto {
            enabled: false,
            reason: None,
            updated_at: Utc::now().to_rfc3339(),
        },
    })
}

pub async fn set_maintenance_state(
    pool: &SqlitePool,
    enabled: bool,
    reason: Option<&str>,
) -> Result<MaintenanceStateDto, ApiError> {
    let now = Utc::now().to_rfc3339();
    let cleaned_reason = reason.map(str::trim).filter(|s| !s.is_empty());
    sqlx::query(
        r#"
        INSERT INTO maintenance_state (id, enabled, reason, updated_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            enabled = excluded.enabled,
            reason = excluded.reason,
            updated_at = excluded.updated_at
        "#,
    )
    .bind(if enabled { 1_i64 } else { 0_i64 })
    .bind(cleaned_reason)
    .bind(&now)
    .execute(pool)
    .await?;

    Ok(MaintenanceStateDto {
        enabled,
        reason: cleaned_reason.map(str::to_string),
        updated_at: now,
    })
}
