use std::env;

use thiserror::Error;

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("variable de entorno obligatoria ausente o vacía: {0}")]
    MissingVar(&'static str),
    #[error("valor inválido para {key}: {detail}")]
    InvalidVar { key: &'static str, detail: String },
}

#[derive(Debug, Clone)]
pub struct AppConfig {
    pub bind_addr: String,
    pub database_url: String,
    pub app_origin: String,
    pub r2_account_id: String,
    pub r2_access_key_id: String,
    pub r2_secret_access_key: String,
    pub r2_bucket: String,
    pub r2_prefix: String,
    pub r2_region: String,
    pub r2_endpoint: String,
    pub max_file_bytes: u64,
    pub max_duration_seconds: u32,
    pub max_concurrent_inference: usize,
    pub max_queue_depth: i64,
    pub presign_put_ttl_seconds: u64,
    pub presign_get_ttl_seconds: u64,
    pub retention_hours: i64,
    pub cleanup_interval_seconds: u64,
    pub rate_limit_uploads_per_hour: i64,
    pub inference_service_url: String,
    pub inference_timeout_seconds: u64,
    pub session_hmac_secret: String,
}

impl AppConfig {
    pub fn from_env() -> Result<Self, ConfigError> {
        let r2_account_id = required_var("R2_ACCOUNT_ID")?;
        let r2_access_key_id = required_var("R2_ACCESS_KEY_ID")?;
        let r2_secret_access_key = required_var("R2_SECRET_ACCESS_KEY")?;
        let r2_bucket = required_var("R2_BUCKET")?;

        let raw_prefix = env::var("R2_PREFIX").unwrap_or_else(|_| "doppler/uploads/".to_string());
        let r2_prefix = normalize_prefix(&raw_prefix);
        if r2_prefix.is_empty() {
            return Err(ConfigError::InvalidVar {
                key: "R2_PREFIX",
                detail: "el prefijo de objetos no puede estar vacío".to_string(),
            });
        }

        let r2_region = env::var("R2_REGION").unwrap_or_else(|_| "auto".to_string());
        let r2_endpoint = match env::var("R2_ENDPOINT") {
            Ok(v) if !v.trim().is_empty() => v.trim().to_string(),
            _ => format!("https://{r2_account_id}.r2.cloudflarestorage.com"),
        };

        let session_hmac_secret = required_var("SESSION_HMAC_SECRET")?;
        if session_hmac_secret.len() < 32 {
            return Err(ConfigError::InvalidVar {
                key: "SESSION_HMAC_SECRET",
                detail: "debe tener al menos 32 caracteres".to_string(),
            });
        }

        Ok(Self {
            bind_addr: env::var("API_BIND_ADDR").unwrap_or_else(|_| "0.0.0.0:8080".to_string()),
            database_url: env::var("DATABASE_URL")
                .unwrap_or_else(|_| "sqlite:///data/doppler.db?mode=rwc".to_string()),
            app_origin: env::var("APP_ORIGIN")
                .unwrap_or_else(|_| "http://localhost:4321".to_string()),
            r2_account_id,
            r2_access_key_id,
            r2_secret_access_key,
            r2_bucket,
            r2_prefix,
            r2_region,
            r2_endpoint,
            max_file_bytes: parse_u64("MAX_FILE_BYTES", 26_214_400)?,
            max_duration_seconds: parse_u32("MAX_DURATION_SECONDS", 120)?,
            max_concurrent_inference: parse_usize("MAX_CONCURRENT_INFERENCE", 1)?.max(1),
            max_queue_depth: parse_i64("MAX_QUEUE_DEPTH", 16)?.max(1),
            presign_put_ttl_seconds: parse_u64("PRESIGN_PUT_TTL_SECONDS", 300)?.clamp(30, 3600),
            presign_get_ttl_seconds: parse_u64("PRESIGN_GET_TTL_SECONDS", 180)?.clamp(30, 3600),
            retention_hours: parse_i64("RETENTION_HOURS", 24)?.max(1),
            cleanup_interval_seconds: parse_u64("CLEANUP_INTERVAL_SECONDS", 300)?.max(15),
            rate_limit_uploads_per_hour: parse_i64("RATE_LIMIT_UPLOADS_PER_HOUR", 60)?.max(1),
            inference_service_url: env::var("INFERENCE_SERVICE_URL")
                .unwrap_or_else(|_| "http://inference:8000".to_string())
                .trim_end_matches('/')
                .to_string(),
            inference_timeout_seconds: parse_u64("INFERENCE_TIMEOUT_SECONDS", 120)?.max(10),
            session_hmac_secret,
        })
    }

    pub fn r2_configured(&self) -> bool {
        !self.r2_account_id.starts_with("replace_with_")
            && !self.r2_access_key_id.starts_with("replace_with_")
            && !self.r2_secret_access_key.starts_with("replace_with_")
            && !self.r2_bucket.is_empty()
    }
}

fn required_var(key: &'static str) -> Result<String, ConfigError> {
    let val = env::var(key).map_err(|_| ConfigError::MissingVar(key))?;
    let trimmed = val.trim();
    if trimmed.is_empty() {
        return Err(ConfigError::MissingVar(key));
    }
    Ok(trimmed.to_string())
}

fn normalize_prefix(raw: &str) -> String {
    let cleaned = raw.trim().trim_start_matches('/');
    if cleaned.is_empty() {
        return String::new();
    }
    if cleaned.ends_with('/') {
        cleaned.to_string()
    } else {
        format!("{cleaned}/")
    }
}

fn parse_u64(key: &'static str, default: u64) -> Result<u64, ConfigError> {
    match env::var(key) {
        Ok(v) if !v.trim().is_empty() => v.trim().parse::<u64>().map_err(|e| ConfigError::InvalidVar {
            key,
            detail: e.to_string(),
        }),
        _ => Ok(default),
    }
}

fn parse_u32(key: &'static str, default: u32) -> Result<u32, ConfigError> {
    match env::var(key) {
        Ok(v) if !v.trim().is_empty() => v.trim().parse::<u32>().map_err(|e| ConfigError::InvalidVar {
            key,
            detail: e.to_string(),
        }),
        _ => Ok(default),
    }
}

fn parse_usize(key: &'static str, default: usize) -> Result<usize, ConfigError> {
    match env::var(key) {
        Ok(v) if !v.trim().is_empty() => v.trim().parse::<usize>().map_err(|e| ConfigError::InvalidVar {
            key,
            detail: e.to_string(),
        }),
        _ => Ok(default),
    }
}

fn parse_i64(key: &'static str, default: i64) -> Result<i64, ConfigError> {
    match env::var(key) {
        Ok(v) if !v.trim().is_empty() => v.trim().parse::<i64>().map_err(|e| ConfigError::InvalidVar {
            key,
            detail: e.to_string(),
        }),
        _ => Ok(default),
    }
}
