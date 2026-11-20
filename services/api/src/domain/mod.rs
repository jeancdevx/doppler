use hmac::{Hmac, Mac};
use rand::RngCore;
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use subtle::ConstantTimeEq;

type HmacSha256 = Hmac<Sha256>;

pub const SESSION_COOKIE_NAME: &str = "doppler_session";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum JobStatus {
    Uploading,
    Queued,
    Analyzing,
    Completed,
    Failed,
}

impl JobStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Uploading => "uploading",
            Self::Queued => "queued",
            Self::Analyzing => "analyzing",
            Self::Completed => "completed",
            Self::Failed => "failed",
        }
    }

    pub fn from_db(s: &str) -> Self {
        match s {
            "uploading" => Self::Uploading,
            "queued" => Self::Queued,
            "analyzing" => Self::Analyzing,
            "completed" => Self::Completed,
            _ => Self::Failed,
        }
    }
}

pub fn generate_opaque_id(num_bytes: usize) -> String {
    let mut buf = vec![0u8; num_bytes];
    rand::rng().fill_bytes(&mut buf);
    hex::encode(buf)
}

pub fn sign_session_token(session_id: &str, secret: &str) -> String {
    let mut mac =
        HmacSha256::new_from_slice(secret.as_bytes()).expect("HMAC acepta cualquier longitud");
    mac.update(session_id.as_bytes());
    let sig = hex::encode(mac.finalize().into_bytes());
    format!("{session_id}.{sig}")
}

pub fn verify_session_token(token: &str, secret: &str) -> Option<String> {
    let (session_id, provided_hex) = token.split_once('.')?;
    if session_id.len() < 16 || provided_hex.len() != 64 {
        return None;
    }
    let provided = hex::decode(provided_hex).ok()?;
    let mut mac =
        HmacSha256::new_from_slice(secret.as_bytes()).expect("HMAC acepta cualquier longitud");
    mac.update(session_id.as_bytes());
    let expected = mac.finalize().into_bytes();
    if expected.as_slice().ct_eq(&provided).into() {
        Some(session_id.to_string())
    } else {
        None
    }
}

pub fn sanitize_filename(raw: &str) -> String {
    let base = raw
        .rsplit(['/', '\\'])
        .next()
        .unwrap_or("audio.wav")
        .trim();
    let cleaned: String = base
        .chars()
        .filter(|c| !c.is_control())
        .take(180)
        .collect();
    if cleaned.is_empty() {
        "audio.wav".to_string()
    } else {
        cleaned
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct LimitsInfo {
    pub allowed_extensions: Vec<&'static str>,
    pub max_file_bytes: u64,
    pub max_duration_seconds: u32,
    pub min_window_seconds: f64,
    pub window_seconds: f64,
    pub hop_seconds: f64,
    pub retention_hours: i64,
    pub max_queue_depth: i64,
    pub max_concurrent_inference: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct SessionResponse {
    pub session_id: String,
    pub limits: LimitsInfo,
}

#[derive(Debug, Deserialize)]
pub struct CreateUploadRequest {
    pub filename: String,
    pub size_bytes: u64,
    pub content_type: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct UploadTarget {
    pub method: &'static str,
    pub url: String,
    pub headers: std::collections::BTreeMap<String, String>,
    pub expires_in_seconds: u64,
}

#[derive(Debug, Serialize)]
pub struct CreateUploadResponse {
    pub job_id: String,
    pub run_id: String,
    pub status: JobStatus,
    pub upload: UploadTarget,
    pub expires_at: String,
    pub retention_hours: i64,
}

#[derive(Debug, Deserialize, Default)]
pub struct ConfirmUploadRequest {
    pub client_upload_ms: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WindowDto {
    pub index: i64,
    pub start_seconds: f64,
    pub end_seconds: f64,
    pub score: f64,
    pub label: String,
    pub margin_vs_threshold: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct MergedIntervalDto {
    pub start_seconds: f64,
    pub end_seconds: f64,
    pub duration_seconds: f64,
    pub window_count: usize,
    pub max_score: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct AudioInfoDto {
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

#[derive(Debug, Clone, Serialize)]
pub struct TimingsDto {
    pub client_upload_ms: Option<f64>,
    pub queue_wait_ms: Option<f64>,
    pub r2_fetch_ms: Option<f64>,
    pub decode_and_prepare_ms: Option<f64>,
    pub inference_ms: Option<f64>,
    pub persist_ms: Option<f64>,
    pub total_processing_ms: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct JobSummaryDto {
    pub job_id: String,
    pub run_id: String,
    pub filename: String,
    pub status: JobStatus,
    pub declared_size_bytes: i64,
    pub actual_size_bytes: Option<i64>,
    pub duration_seconds: Option<f64>,
    pub windows_total: i64,
    pub windows_positive: i64,
    pub short_clip: bool,
    pub error_code: Option<String>,
    pub error_message: Option<String>,
    pub created_at: String,
    pub completed_at: Option<String>,
    pub expires_at: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct JobDetailDto {
    pub job_id: String,
    pub run_id: String,
    pub filename: String,
    pub status: JobStatus,
    pub queue_position: Option<i64>,
    pub declared_size_bytes: i64,
    pub actual_size_bytes: Option<i64>,
    pub error_code: Option<String>,
    pub error_message: Option<String>,
    pub audio_sha256: Option<String>,
    pub model_sha256: Option<String>,
    pub contract_version: Option<String>,
    pub contract_sha256: Option<String>,
    pub threshold: Option<f64>,
    pub score_type: Option<String>,
    pub audio: Option<AudioInfoDto>,
    pub windows_total: i64,
    pub windows_positive: i64,
    pub positive_coverage_seconds: f64,
    pub positive_coverage_note: &'static str,
    pub merged_positive_intervals: Vec<MergedIntervalDto>,
    pub windows: Vec<WindowDto>,
    pub short_clip: bool,
    pub short_clip_message: Option<String>,
    pub timings: TimingsDto,
    pub created_at: String,
    pub confirmed_at: Option<String>,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub expires_at: String,
}

#[derive(Debug, Serialize)]
pub struct AudioUrlResponse {
    pub job_id: String,
    pub url: String,
    pub expires_in_seconds: u64,
    pub content_type: String,
}

pub fn merge_positive_intervals(windows: &[WindowDto]) -> (Vec<MergedIntervalDto>, f64) {
    let mut positives: Vec<&WindowDto> = windows
        .iter()
        .filter(|w| w.label == "EMERGENCY")
        .collect();
    if positives.is_empty() {
        return (Vec::new(), 0.0);
    }
    positives.sort_by(|a, b| a.start_seconds.total_cmp(&b.start_seconds));

    let mut merged: Vec<MergedIntervalDto> = Vec::new();
    for win in positives {
        if let Some(last) = merged.last_mut() {
            if win.start_seconds <= last.end_seconds + 1e-6 {
                last.end_seconds = last.end_seconds.max(win.end_seconds);
                last.duration_seconds = (last.end_seconds - last.start_seconds).max(0.0);
                last.window_count += 1;
                last.max_score = last.max_score.max(win.score);
                continue;
            }
        }
        merged.push(MergedIntervalDto {
            start_seconds: win.start_seconds,
            end_seconds: win.end_seconds,
            duration_seconds: (win.end_seconds - win.start_seconds).max(0.0),
            window_count: 1,
            max_score: win.score,
        });
    }
    let total_coverage: f64 = merged.iter().map(|m| m.duration_seconds).sum();
    (merged, total_coverage)
}
