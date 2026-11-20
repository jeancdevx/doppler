use std::str::FromStr;

use sqlx::sqlite::{SqliteConnectOptions, SqliteJournalMode, SqlitePoolOptions, SqliteSynchronous};
use tokio::net::TcpListener;
use tracing_subscriber::EnvFilter;

use doppler_api::config::AppConfig;
use doppler_api::db;
use doppler_api::inference::InferenceClient;
use doppler_api::state::AppState;
use doppler_api::storage::R2Storage;
use doppler_api::{build_app, worker};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let _ = dotenvy::dotenv();

    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("doppler_api=info,tower_http=info")),
        )
        .init();

    let cfg = AppConfig::from_env()?;
    tracing::info!(
        bind_addr = %cfg.bind_addr,
        app_origin = %cfg.app_origin,
        r2_bucket = %cfg.r2_bucket,
        r2_prefix = %cfg.r2_prefix,
        max_file_bytes = cfg.max_file_bytes,
        max_duration_seconds = cfg.max_duration_seconds,
        max_queue_depth = cfg.max_queue_depth,
        max_concurrent_inference = cfg.max_concurrent_inference,
        retention_hours = cfg.retention_hours,
        "Iniciando Doppler API (Rust / Axum)"
    );

    let connect_options = SqliteConnectOptions::from_str(&cfg.database_url)?
        .create_if_missing(true)
        .journal_mode(SqliteJournalMode::Wal)
        .synchronous(SqliteSynchronous::Normal)
        .foreign_keys(true);

    let pool = SqlitePoolOptions::new()
        .max_connections(8)
        .connect_with(connect_options)
        .await?;

    sqlx::migrate!("./migrations").run(&pool).await?;

    let recovered = db::recover_interrupted_jobs(&pool).await?;
    if recovered > 0 {
        tracing::warn!(recovered = recovered, "Trabajos interrumpidos reencolados tras reinicio");
    }

    let r2 = R2Storage::new(&cfg);
    let inference = InferenceClient::new(
        cfg.inference_service_url.clone(),
        cfg.inference_timeout_seconds,
    )?;

    let bind_addr = cfg.bind_addr.clone();
    let state = AppState::new(cfg, pool, r2, inference);

    worker::spawn_dispatcher(state.clone());
    worker::spawn_cleanup_task(state.clone());

    let app = build_app(state);
    let listener = TcpListener::bind(&bind_addr).await?;
    tracing::info!(addr = %bind_addr, "Doppler API escuchando");
    axum::serve(listener, app).await?;
    Ok(())
}
