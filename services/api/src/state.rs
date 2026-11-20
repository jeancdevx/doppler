use std::sync::Arc;

use sqlx::SqlitePool;
use tokio::sync::Notify;

use crate::config::AppConfig;
use crate::inference::InferenceClient;
use crate::storage::R2Storage;

#[derive(Clone)]
pub struct AppState {
    pub config: Arc<AppConfig>,
    pub db: SqlitePool,
    pub r2: R2Storage,
    pub inference: InferenceClient,
    pub job_notify: Arc<Notify>,
}

impl AppState {
    pub fn new(
        config: AppConfig,
        db: SqlitePool,
        r2: R2Storage,
        inference: InferenceClient,
    ) -> Self {
        Self {
            config: Arc::new(config),
            db,
            r2,
            inference,
            job_notify: Arc::new(Notify::new()),
        }
    }
}
