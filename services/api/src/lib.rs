pub mod config;
pub mod db;
pub mod domain;
pub mod error;
pub mod inference;
pub mod maintenance;
pub mod routes;
pub mod state;
pub mod storage;
pub mod worker;

use axum::http::{header, HeaderName, HeaderValue, Method};
use axum::Router;
use tower_http::cors::CorsLayer;
use tower_http::limit::RequestBodyLimitLayer;
use tower_http::trace::TraceLayer;

use crate::state::AppState;

pub fn build_app(state: AppState) -> Router {
    let origin = HeaderValue::from_str(&state.config.app_origin)
        .unwrap_or_else(|_| HeaderValue::from_static("http://localhost:4321"));

    let admin_header = HeaderName::from_static("x-admin-token");
    let cors = CorsLayer::new()
        .allow_origin(origin)
        .allow_methods([
            Method::GET,
            Method::POST,
            Method::PATCH,
            Method::DELETE,
            Method::OPTIONS,
        ])
        .allow_headers([header::CONTENT_TYPE, header::ACCEPT, admin_header])
        .allow_credentials(true);

    Router::new()
        .nest("/api", routes::api_router())
        .with_state(state)
        .layer(RequestBodyLimitLayer::new(2 * 1024 * 1024))
        .layer(cors)
        .layer(TraceLayer::new_for_http())
}
