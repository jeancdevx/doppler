use chrono::Utc;
use serde::{Deserialize, Serialize};
use sqlx::{FromRow, SqlitePool};

use crate::domain::generate_opaque_id;
use crate::error::ApiError;

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct ModelDeploymentRow {
    pub id: String,
    pub action: String,
    pub package_version: String,
    pub model_sha256: Option<String>,
    pub contract_version: Option<String>,
    pub contract_sha256: Option<String>,
    pub previous_model_sha256: Option<String>,
    pub status: String,
    pub reason: String,
    pub details_json: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Deserialize)]
pub struct RecordDeploymentRequest {
    pub action: String,
    pub package_version: String,
    pub model_sha256: Option<String>,
    pub contract_version: Option<String>,
    pub contract_sha256: Option<String>,
    pub previous_model_sha256: Option<String>,
    pub status: String,
    pub reason: String,
    pub details_json: Option<String>,
}

pub async fn list_recent_deployments(
    pool: &SqlitePool,
    limit: i64,
) -> Result<Vec<ModelDeploymentRow>, ApiError> {
    sqlx::query_as::<_, ModelDeploymentRow>(
        "SELECT * FROM model_deployments ORDER BY created_at DESC LIMIT ?",
    )
    .bind(limit)
    .fetch_all(pool)
    .await
    .map_err(ApiError::from)
}

pub async fn record_model_deployment(
    pool: &SqlitePool,
    req: &RecordDeploymentRequest,
) -> Result<ModelDeploymentRow, ApiError> {
    if !matches!(
        req.action.as_str(),
        "validate" | "activate" | "rollback" | "reject"
    ) {
        return Err(ApiError::Validation("action inválida.".to_string()));
    }
    if !matches!(req.status.as_str(), "ok" | "failed" | "rolled_back") {
        return Err(ApiError::Validation("status inválido.".to_string()));
    }

    let id = format!("dep_{}", generate_opaque_id(8));
    let now = Utc::now().to_rfc3339();
    sqlx::query(
        r#"
        INSERT INTO model_deployments (
            id, action, package_version, model_sha256, contract_version,
            contract_sha256, previous_model_sha256, status, reason, details_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(&id)
    .bind(&req.action)
    .bind(&req.package_version)
    .bind(&req.model_sha256)
    .bind(&req.contract_version)
    .bind(&req.contract_sha256)
    .bind(&req.previous_model_sha256)
    .bind(&req.status)
    .bind(&req.reason)
    .bind(&req.details_json)
    .bind(&now)
    .execute(pool)
    .await?;

    Ok(ModelDeploymentRow {
        id,
        action: req.action.clone(),
        package_version: req.package_version.clone(),
        model_sha256: req.model_sha256.clone(),
        contract_version: req.contract_version.clone(),
        contract_sha256: req.contract_sha256.clone(),
        previous_model_sha256: req.previous_model_sha256.clone(),
        status: req.status.clone(),
        reason: req.reason.clone(),
        details_json: req.details_json.clone(),
        created_at: now,
    })
}
