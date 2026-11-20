pub mod config;
pub mod db;
pub mod domain;
pub mod error;
pub mod inference;
pub mod routes;
pub mod state;
pub mod storage;
pub mod worker;

use axum::http::{header, HeaderValue, Method};
use axum::Router;
use tower_http::cors::CorsLayer;
use tower_http::limit::RequestBodyLimitLayer;
use tower_http::trace::TraceLayer;

use crate::state::AppState;

pub fn build_app(state: AppState) -> Router {
    let origin = HeaderValue::from_str(&state.config.app_origin)
        .unwrap_or_else(|_| HeaderValue::from_static("http://localhost:4321"));

    let cors = CorsLayer::new()
        .allow_origin(origin)
        .allow_methods([Method::GET, Method::POST, Method::DELETE, Method::OPTIONS])
        .allow_headers([header::CONTENT_TYPE, header::ACCEPT])
        .allow_credentials(true);

    Router::new()
        .nest("/api", routes::api_router())
        .with_state(state)
        .layer(RequestBodyLimitLayer::new(1024 * 1024))
        .layer(cors)
        .layer(TraceLayer::new_for_http())
}
