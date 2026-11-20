use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Serialize;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ApiError {
    #[error("error de configuración: {0}")]
    Config(String),
    #[error("solicitud inválida: {0}")]
    Validation(String),
    #[error("límite excedido: {0}")]
    LimitExceeded(String),
    #[error("cola llena: {0}")]
    QueueFull(String),
    #[error("cuota excedida: {0}")]
    RateLimited(String),
    #[error("sesión no autorizada: {0}")]
    Unauthorized(String),
    #[error("recurso no encontrado: {0}")]
    NotFound(String),
    #[error("conflicto de estado: {0}")]
    Conflict(String),
    #[error("error de almacenamiento R2: {0}")]
    R2(String),
    #[error("error del servicio de inferencia: {0}")]
    Inference(String),
    #[error("en mantenimiento controlado: {0}")]
    Maintenance(String),
    #[error("error de base de datos: {0}")]
    Database(#[from] sqlx::Error),
    #[error("error interno: {0}")]
    Internal(String),
}

#[derive(Debug, Serialize)]
struct ErrorEnvelope {
    error: ErrorBody,
}

#[derive(Debug, Serialize)]
struct ErrorBody {
    code: &'static str,
    message: String,
}

impl ApiError {
    pub fn status_and_code(&self) -> (StatusCode, &'static str) {
        match self {
            Self::Config(_) => (StatusCode::SERVICE_UNAVAILABLE, "config_error"),
            Self::Validation(_) => (StatusCode::BAD_REQUEST, "validation_error"),
            Self::LimitExceeded(_) => (StatusCode::PAYLOAD_TOO_LARGE, "limit_exceeded"),
            Self::QueueFull(_) => (StatusCode::TOO_MANY_REQUESTS, "queue_full"),
            Self::RateLimited(_) => (StatusCode::TOO_MANY_REQUESTS, "rate_limited"),
            Self::Unauthorized(_) => (StatusCode::UNAUTHORIZED, "unauthorized"),
            Self::NotFound(_) => (StatusCode::NOT_FOUND, "not_found"),
            Self::Conflict(_) => (StatusCode::CONFLICT, "invalid_state_transition"),
            Self::R2(_) => (StatusCode::BAD_GATEWAY, "r2_error"),
            Self::Inference(_) => (StatusCode::BAD_GATEWAY, "inference_error"),
            Self::Maintenance(_) => (StatusCode::SERVICE_UNAVAILABLE, "maintenance_mode"),
            Self::Database(_) => (StatusCode::INTERNAL_SERVER_ERROR, "database_error"),
            Self::Internal(_) => (StatusCode::INTERNAL_SERVER_ERROR, "internal_error"),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let (status, code) = self.status_and_code();
        let message = match &self {
            Self::Database(_) => {
                tracing::error!(error = %self, "Database error");
                "Error interno al consultar el almacenamiento de trabajos.".to_string()
            }
            _ => self.to_string(),
        };
        (status, Json(ErrorEnvelope { error: ErrorBody { code, message } })).into_response()
    }
}
