use axum::http::HeaderMap;
use axum_extra::extract::cookie::{Cookie, CookieJar, SameSite};

use crate::config::AppConfig;
use crate::db;
use crate::domain::{
    generate_opaque_id, sign_session_token, verify_session_token, LimitsInfo, SESSION_COOKIE_NAME,
};
use crate::error::ApiError;
use crate::maintenance;
use crate::state::AppState;

pub(super) fn limits_from_config(cfg: &AppConfig) -> LimitsInfo {
    LimitsInfo {
        allowed_extensions: vec![".wav"],
        max_file_bytes: cfg.max_file_bytes,
        max_duration_seconds: cfg.max_duration_seconds,
        min_window_seconds: 3.0,
        window_seconds: 3.0,
        hop_seconds: 1.5,
        retention_hours: cfg.retention_hours,
        max_queue_depth: cfg.max_queue_depth,
        max_concurrent_inference: cfg.max_concurrent_inference,
    }
}

pub(super) fn build_session_cookie(session_id: &str, cfg: &AppConfig) -> Cookie<'static> {
    let signed = sign_session_token(session_id, &cfg.session_hmac_secret);
    let is_https = cfg.app_origin.starts_with("https://");
    Cookie::build((SESSION_COOKIE_NAME, signed))
        .path("/")
        .http_only(true)
        .same_site(SameSite::Lax)
        .secure(is_https)
        .max_age(time::Duration::days(7))
        .build()
}

pub(super) fn extract_verified_session(jar: &CookieJar, cfg: &AppConfig) -> Option<String> {
    let raw = jar.get(SESSION_COOKIE_NAME)?.value();
    verify_session_token(raw, &cfg.session_hmac_secret)
}

pub(super) fn require_admin(headers: &HeaderMap, cfg: &AppConfig) -> Result<(), ApiError> {
    let provided = headers.get("x-admin-token").and_then(|v| v.to_str().ok());
    maintenance::verify_admin_token(provided, cfg.admin_api_token.as_deref())
}

pub(super) async fn resolve_or_create_session(
    jar: CookieJar,
    state: &AppState,
) -> Result<(CookieJar, String), ApiError> {
    if let Some(session_id) = extract_verified_session(&jar, &state.config) {
        db::ensure_session(&state.db, &session_id).await?;
        return Ok((jar, session_id));
    }
    let session_id = generate_opaque_id(16);
    db::ensure_session(&state.db, &session_id).await?;
    let cookie = build_session_cookie(&session_id, &state.config);
    Ok((jar.add(cookie), session_id))
}

pub(super) async fn require_session(jar: &CookieJar, state: &AppState) -> Result<String, ApiError> {
    let Some(session_id) = extract_verified_session(jar, &state.config) else {
        return Err(ApiError::Unauthorized(
            "Se requiere una sesión válida de Doppler para acceder a este recurso.".to_string(),
        ));
    };
    db::ensure_session(&state.db, &session_id).await?;
    Ok(session_id)
}
