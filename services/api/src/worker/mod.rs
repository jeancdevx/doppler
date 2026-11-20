use std::sync::Arc;
use std::time::{Duration, Instant};

use tokio::sync::Semaphore;

use crate::db;
use crate::state::AppState;

pub fn spawn_dispatcher(state: AppState) {
    let permits = state.config.max_concurrent_inference.max(1);
    let semaphore = Arc::new(Semaphore::new(permits));

    tokio::spawn(async move {
        tracing::info!(max_concurrent_inference = permits, "Despachador de inferencia iniciado");
        loop {
            let permit = match semaphore.clone().acquire_owned().await {
                Ok(p) => p,
                Err(_) => break,
            };

            match db::claim_next_queued_job(&state.db).await {
                Ok(Some(job)) => {
                    let worker_state = state.clone();
                    tokio::spawn(async move {
                        let _permit = permit;
                        process_job(worker_state, job).await;
                    });
                }
                Ok(None) => {
                    drop(permit);
                    tokio::select! {
                        _ = state.job_notify.notified() => {}
                        _ = tokio::time::sleep(Duration::from_millis(500)) => {}
                    }
                }
                Err(err) => {
                    drop(permit);
                    tracing::error!(error = %err, "Error reservando trabajo de la cola SQLite");
                    tokio::time::sleep(Duration::from_secs(1)).await;
                }
            }
        }
    });
}

async fn process_job(state: AppState, job: db::JobRow) {
    let started = Instant::now();
    let job_id = job.id.clone();
    let object_key = job.object_key.clone();
    let queue_wait_ms = job.queue_wait_ms.unwrap_or(0.0);

    tracing::info!(job_id = %job_id, run_id = %job.run_id, "Procesando trabajo desde R2");

    let fetch_start = Instant::now();
    let wav_bytes = match state
        .r2
        .download_bounded(&object_key, state.config.max_file_bytes)
        .await
    {
        Ok(bytes) => bytes,
        Err(err) => {
            let (_, code) = err.status_and_code();
            tracing::warn!(job_id = %job_id, code = code, error = %err, "Fallo descargando objeto de R2");
            let _ = db::mark_job_failed(&state.db, &job_id, "analyzing", code, &err.to_string()).await;
            return;
        }
    };
    let r2_fetch_ms = fetch_start.elapsed().as_secs_f64() * 1000.0;

    let result = match state.inference.infer(wav_bytes).await {
        Ok(res) => res,
        Err(err) => {
            tracing::warn!(job_id = %job_id, code = %err.code, message = %err.message, "Inferencia fallida");
            let _ = db::mark_job_failed(&state.db, &job_id, "analyzing", &err.code, &err.message).await;
            return;
        }
    };

    let elapsed_before_persist = started.elapsed().as_secs_f64() * 1000.0;
    if let Err(err) = db::complete_job_with_result(
        &state.db,
        &job_id,
        &result,
        r2_fetch_ms,
        queue_wait_ms,
        elapsed_before_persist,
    )
    .await
    {
        tracing::error!(job_id = %job_id, error = %err, "Error persistiendo resultado en SQLite");
        let _ = db::mark_job_failed(
            &state.db,
            &job_id,
            "analyzing",
            "database_error",
            "No se pudo persistir el resultado del análisis.",
        )
        .await;
    } else {
        tracing::info!(
            job_id = %job_id,
            windows_total = result.windows_total,
            windows_positive = result.windows_positive,
            r2_fetch_ms = r2_fetch_ms,
            decode_and_prepare_ms = result.timings.decode_and_prepare_ms,
            inference_ms = result.timings.inference_ms,
            "Trabajo completado"
        );
    }
}

pub fn spawn_cleanup_task(state: AppState) {
    let interval_secs = state.config.cleanup_interval_seconds;
    tokio::spawn(async move {
        let mut ticker = tokio::time::interval(Duration::from_secs(interval_secs));
        loop {
            ticker.tick().await;
            if let Err(err) = run_cleanup_once(&state).await {
                tracing::warn!(error = %err, "Error en ciclo de limpieza por retención");
            }
        }
    });
}

pub async fn run_cleanup_once(state: &AppState) -> Result<usize, crate::error::ApiError> {
    let expired = db::find_expired_or_abandoned_jobs(&state.db, 30).await?;
    let mut cleaned = 0usize;
    for rec in expired {
        if state.r2.is_owned_key(&rec.object_key) {
            if let Err(err) = state.r2.delete_object(&rec.object_key).await {
                tracing::warn!(job_id = %rec.id, error = %err, "No se pudo borrar objeto expirado en R2");
                continue;
            }
        }
        db::hard_delete_job(&state.db, &rec.id).await?;
        cleaned += 1;
    }
    if cleaned > 0 {
        tracing::info!(cleaned = cleaned, "Limpieza por retención completada");
    }
    Ok(cleaned)
}
