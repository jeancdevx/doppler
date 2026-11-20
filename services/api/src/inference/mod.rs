use std::time::Duration;

use bytes::Bytes;
use serde::{Deserialize, Serialize};

use crate::error::ApiError;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct InferenceHealth {
    pub status: String,
    pub ready: bool,
    pub model_loaded: bool,
    pub model_sha256: Option<String>,
    pub contract_version: String,
    pub contract_sha256: Option<String>,
    pub threshold: Option<f64>,
    pub score_type: Option<String>,
    pub input_shape: Option<Vec<i64>>,
    pub torch_version: String,
    pub torch_num_threads: i64,
    pub startup_load_ms: Option<f64>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct InferenceWindow {
    pub index: i64,
    pub start_seconds: f64,
    pub end_seconds: f64,
    pub score: f64,
    pub label: String,
    pub margin_vs_threshold: f64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct InferenceAudioMetadata {
    pub original_sample_rate: i64,
    pub original_channels: i64,
    pub prepared_sample_rate: i64,
    pub prepared_channels: i64,
    pub duration_seconds: f64,
    pub prepared_samples: i64,
    pub peak_before_normalization: f64,
    pub peak_after_normalization: f64,
    pub rms_after_normalization: f64,
    pub downmix_cancellation_candidate: bool,
    pub discarded_tail_samples: i64,
    pub discarded_tail_seconds: f64,
    pub window_seconds: f64,
    pub hop_seconds: f64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct InferenceTimings {
    pub decode_and_prepare_ms: f64,
    pub inference_ms: f64,
    pub total_ms: f64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct InferenceResult {
    pub audio_sha256: String,
    pub model_sha256: String,
    pub contract_version: String,
    pub contract_sha256: String,
    pub threshold: f64,
    pub score_type: String,
    pub audio: InferenceAudioMetadata,
    pub windows: Vec<InferenceWindow>,
    pub windows_total: i64,
    pub windows_positive: i64,
    pub timings: InferenceTimings,
    pub short_clip: bool,
    pub short_clip_message: Option<String>,
}

#[derive(Debug, Deserialize)]
struct FastApiErrorEnvelope {
    detail: FastApiErrorDetail,
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum FastApiErrorDetail {
    Structured { code: String, message: String },
    Plain(String),
}

#[derive(Debug, Clone)]
pub struct StructuredInferenceError {
    pub code: String,
    pub message: String,
}

#[derive(Clone)]
pub struct InferenceClient {
    http: reqwest::Client,
    base_url: String,
}

impl InferenceClient {
    pub fn new(base_url: String, timeout_seconds: u64) -> Result<Self, ApiError> {
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(timeout_seconds))
            .connect_timeout(Duration::from_secs(10))
            .build()
            .map_err(|e| ApiError::Internal(format!("no se pudo crear cliente HTTP interno: {e}")))?;
        Ok(Self { http, base_url })
    }

    pub async fn health(&self) -> Result<InferenceHealth, ApiError> {
        let url = format!("{}/health", self.base_url);
        let resp = self
            .http
            .get(url)
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .map_err(|e| ApiError::Inference(format!("servicio de inferencia no responde: {e}")))?;

        resp.json::<InferenceHealth>()
            .await
            .map_err(|e| ApiError::Inference(format!("respuesta /health inválida: {e}")))
    }

    pub async fn infer(&self, wav_bytes: Bytes) -> Result<InferenceResult, StructuredInferenceError> {
        let url = format!("{}/infer", self.base_url);
        let resp = self
            .http
            .post(url)
            .header("content-type", "application/octet-stream")
            .body(wav_bytes)
            .send()
            .await
            .map_err(|e| StructuredInferenceError {
                code: "inference_error".to_string(),
                message: format!("No se pudo comunicar con el servicio de inferencia: {e}"),
            })?;

        let status = resp.status();
        if status.is_success() {
            resp.json::<InferenceResult>().await.map_err(|e| StructuredInferenceError {
                code: "inference_error".to_string(),
                message: format!("Respuesta de inferencia con formato inesperado: {e}"),
            })
        } else {
            let text = resp.text().await.unwrap_or_default();
            if let Ok(env) = serde_json::from_str::<FastApiErrorEnvelope>(&text) {
                match env.detail {
                    FastApiErrorDetail::Structured { code, message } => {
                        return Err(StructuredInferenceError { code, message });
                    }
                    FastApiErrorDetail::Plain(message) => {
                        return Err(StructuredInferenceError {
                            code: "inference_error".to_string(),
                            message,
                        });
                    }
                }
            }
            Err(StructuredInferenceError {
                code: "inference_error".to_string(),
                message: format!("El servicio de inferencia respondió con HTTP {status}."),
            })
        }
    }
}
