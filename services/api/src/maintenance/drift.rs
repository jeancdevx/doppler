use std::collections::{BTreeMap, HashMap};

use chrono::{Duration, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{FromRow, SqlitePool};

use crate::domain::generate_opaque_id;
use crate::error::ApiError;
use crate::maintenance::telemetry::summarize_f64;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NumericReferenceFeature {
    pub unit: String,
    pub samples: Vec<f64>,
    pub scale: f64,
    pub threshold_normalized_w1: f64,
    pub comparable: bool,
    pub note: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CategoricalReferenceFeature {
    pub proportions: BTreeMap<String, f64>,
    pub threshold_max_abs_diff: f64,
    pub comparable: bool,
    pub note: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriftReferencePayload {
    pub id: String,
    pub version: String,
    pub name: String,
    pub provenance: String,
    pub observation_unit: String,
    pub file_count: i64,
    pub source_group_count: i64,
    pub representative_status: String,
    pub extraction_version: String,
    pub model_sha256: Option<String>,
    pub contract_version: Option<String>,
    pub contract_sha256: Option<String>,
    pub min_observations: i64,
    pub calibration_note: Option<String>,
    pub input_numeric: BTreeMap<String, NumericReferenceFeature>,
    pub input_categorical: BTreeMap<String, CategoricalReferenceFeature>,
    pub output_numeric: BTreeMap<String, NumericReferenceFeature>,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct DriftReferenceSummary {
    pub id: String,
    pub version: String,
    pub name: String,
    pub provenance: String,
    pub observation_unit: String,
    pub file_count: i64,
    pub source_group_count: i64,
    pub representative_status: String,
    pub extraction_version: String,
    pub model_sha256: Option<String>,
    pub contract_version: Option<String>,
    pub contract_sha256: Option<String>,
    pub min_observations: i64,
    pub is_active: i64,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FeatureDriftMetric {
    pub feature: String,
    pub group: String,
    pub unit: String,
    pub method: String,
    pub n_ref: usize,
    pub n_obs: usize,
    pub statistic: Option<f64>,
    pub normalized_statistic: Option<f64>,
    pub threshold: f64,
    pub ref_mean: Option<f64>,
    pub obs_mean: Option<f64>,
    pub alerted: bool,
    pub status: String,
    pub note: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriftEvaluationDto {
    pub id: String,
    pub reference_id: Option<String>,
    pub evaluated_at: String,
    pub window_days: i64,
    pub sample_count: i64,
    pub status: String,
    pub representative_status: String,
    pub input_drift_detected: bool,
    pub output_drift_detected: bool,
    pub summary: String,
    pub features: Vec<FeatureDriftMetric>,
    pub warning_note: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct DriftStatusResponseDto {
    pub active_reference: Option<DriftReferenceSummary>,
    pub representative_status: String,
    pub latest_evaluation: Option<DriftEvaluationDto>,
    pub recent_evaluations: Vec<DriftEvaluationDto>,
}

#[derive(Debug, Clone, FromRow)]
struct DriftEvalDbRow {
    id: String,
    reference_id: Option<String>,
    evaluated_at: String,
    window_days: i64,
    sample_count: i64,
    status: String,
    representative_status: String,
    input_drift_detected: i64,
    output_drift_detected: i64,
    summary: String,
    details_json: String,
}

#[derive(Debug, Clone, FromRow)]
pub struct DriftObservationRow {
    pub job_id: String,
    pub model_sha256: Option<String>,
    pub contract_sha256: Option<String>,
    pub extraction_version: Option<String>,
    pub original_sample_rate: Option<i64>,
    pub original_channels: Option<i64>,
    pub duration_seconds: Option<f64>,
    pub peak_before_normalization: Option<f64>,
    pub rms_before_normalization: Option<f64>,
    pub silence_ratio: Option<f64>,
    pub clipping_ratio: Option<f64>,
    pub downmix_cancellation_candidate: i64,
    pub short_clip: i64,
    pub logmel_mean: Option<f64>,
    pub logmel_std: Option<f64>,
    pub spectral_centroid_hz: Option<f64>,
    pub positive_window_ratio: Option<f64>,
    pub score_mean: Option<f64>,
    pub score_max: Option<f64>,
}

pub fn wasserstein_1d(a: &[f64], b: &[f64]) -> Option<f64> {
    let mut xs: Vec<f64> = a.iter().copied().filter(|v| v.is_finite()).collect();
    let mut ys: Vec<f64> = b.iter().copied().filter(|v| v.is_finite()).collect();
    if xs.is_empty() || ys.is_empty() {
        return None;
    }
    xs.sort_by(f64::total_cmp);
    ys.sort_by(f64::total_cmp);

    let mut all = Vec::with_capacity(xs.len() + ys.len());
    all.extend_from_slice(&xs);
    all.extend_from_slice(&ys);
    all.sort_by(f64::total_cmp);

    let (n_x, n_y) = (xs.len() as f64, ys.len() as f64);
    let (mut i, mut j, mut area) = (0usize, 0usize, 0.0_f64);

    for w in all.windows(2) {
        let delta = w[1] - w[0];
        if delta <= 0.0 {
            continue;
        }
        while i < xs.len() && xs[i] <= w[0] {
            i += 1;
        }
        while j < ys.len() && ys[j] <= w[0] {
            j += 1;
        }
        area += ((i as f64) / n_x - (j as f64) / n_y).abs() * delta;
    }
    Some(area)
}

pub async fn import_drift_reference(
    pool: &SqlitePool,
    payload: DriftReferencePayload,
) -> Result<DriftReferenceSummary, ApiError> {
    if payload.id.trim().is_empty() || payload.version.trim().is_empty() {
        return Err(ApiError::Validation(
            "La referencia de drift debe incluir id y version.".to_string(),
        ));
    }
    if payload.observation_unit != "file" {
        return Err(ApiError::Validation(
            "La unidad de observación debe ser 'file' para no tratar ventanas solapadas como independientes."
                .to_string(),
        ));
    }
    if !matches!(
        payload.representative_status.as_str(),
        "pending_representative_corpus" | "synthetic_demo" | "representative_validated"
    ) {
        return Err(ApiError::Validation(
            "representative_status inválido.".to_string(),
        ));
    }
    if payload.min_observations < 3 {
        return Err(ApiError::Validation(
            "min_observations debe ser al menos 3 archivos.".to_string(),
        ));
    }

    let json = serde_json::to_string(&payload)
        .map_err(|e| ApiError::Internal(format!("error serializando referencia drift: {e}")))?;
    let now = Utc::now().to_rfc3339();

    let mut tx = pool.begin().await?;
    sqlx::query("UPDATE drift_references SET is_active = 0 WHERE is_active = 1")
        .execute(&mut *tx)
        .await?;

    sqlx::query(
        r#"
        INSERT INTO drift_references (
            id, version, name, provenance, observation_unit, file_count, source_group_count,
            representative_status, extraction_version, model_sha256, contract_version,
            contract_sha256, min_observations, reference_json, is_active, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(id) DO UPDATE SET
            version = excluded.version,
            name = excluded.name,
            provenance = excluded.provenance,
            observation_unit = excluded.observation_unit,
            file_count = excluded.file_count,
            source_group_count = excluded.source_group_count,
            representative_status = excluded.representative_status,
            extraction_version = excluded.extraction_version,
            model_sha256 = excluded.model_sha256,
            contract_version = excluded.contract_version,
            contract_sha256 = excluded.contract_sha256,
            min_observations = excluded.min_observations,
            reference_json = excluded.reference_json,
            is_active = 1,
            created_at = excluded.created_at
        "#,
    )
    .bind(&payload.id)
    .bind(&payload.version)
    .bind(&payload.name)
    .bind(&payload.provenance)
    .bind(&payload.observation_unit)
    .bind(payload.file_count)
    .bind(payload.source_group_count)
    .bind(&payload.representative_status)
    .bind(&payload.extraction_version)
    .bind(&payload.model_sha256)
    .bind(&payload.contract_version)
    .bind(&payload.contract_sha256)
    .bind(payload.min_observations)
    .bind(&json)
    .bind(&now)
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;

    sqlx::query_as::<_, DriftReferenceSummary>(
        r#"
        SELECT id, version, name, provenance, observation_unit, file_count, source_group_count,
               representative_status, extraction_version, model_sha256, contract_version,
               contract_sha256, min_observations, is_active, created_at
        FROM drift_references WHERE id = ?
        "#,
    )
    .bind(&payload.id)
    .fetch_one(pool)
    .await
    .map_err(ApiError::from)
}

pub async fn get_active_drift_reference(
    pool: &SqlitePool,
) -> Result<Option<(DriftReferenceSummary, DriftReferencePayload)>, ApiError> {
    let row: Option<(String,)> = sqlx::query_as(
        "SELECT reference_json FROM drift_references WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1",
    )
    .fetch_optional(pool)
    .await?;

    let Some((raw_json,)) = row else {
        return Ok(None);
    };
    let summary = sqlx::query_as::<_, DriftReferenceSummary>(
        r#"
        SELECT id, version, name, provenance, observation_unit, file_count, source_group_count,
               representative_status, extraction_version, model_sha256, contract_version,
               contract_sha256, min_observations, is_active, created_at
        FROM drift_references WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1
        "#,
    )
    .fetch_one(pool)
    .await?;
    let payload: DriftReferencePayload = serde_json::from_str(&raw_json)
        .map_err(|e| ApiError::Internal(format!("referencia drift corrupta en SQLite: {e}")))?;
    Ok(Some((summary, payload)))
}

pub async fn evaluate_drift_and_store(
    pool: &SqlitePool,
    window_days: i64,
    active_model_sha: Option<&str>,
) -> Result<DriftEvaluationDto, ApiError> {
    let eval_id = format!("drift_{}", generate_opaque_id(8));
    let evaluated_at = Utc::now().to_rfc3339();
    let cutoff = (Utc::now() - Duration::days(window_days.max(1))).to_rfc3339();

    let Some((ref_summary, ref_payload)) = get_active_drift_reference(pool).await? else {
        let dto = DriftEvaluationDto {
            id: eval_id,
            reference_id: None,
            evaluated_at,
            window_days,
            sample_count: 0,
            status: "no_reference".to_string(),
            representative_status: "pending_representative_corpus".to_string(),
            input_drift_detected: false,
            output_drift_detected: false,
            summary: "Sin referencia congelada cargada. Estado: referencia representativa pendiente.".to_string(),
            features: Vec::new(),
            warning_note: "Una alerta de drift inicia una investigación; no demuestra pérdida automática de F1 ni activa reentrenamiento.".to_string(),
        };
        persist_drift_eval(pool, &dto).await?;
        return Ok(dto);
    };

    let obs_rows = sqlx::query_as::<_, DriftObservationRow>(
        r#"
        SELECT job_id, model_sha256, contract_sha256, extraction_version,
               original_sample_rate, original_channels, duration_seconds,
               peak_before_normalization, rms_before_normalization,
               silence_ratio, clipping_ratio, downmix_cancellation_candidate,
               short_clip, logmel_mean, logmel_std, spectral_centroid_hz,
               positive_window_ratio, score_mean, score_max
        FROM job_telemetry_history
        WHERE outcome = 'completed' AND recorded_at >= ?
        ORDER BY recorded_at DESC
        "#,
    )
    .bind(&cutoff)
    .fetch_all(pool)
    .await?;

    if let (Some(ref_sha), Some(cur_sha)) = (ref_payload.model_sha256.as_deref(), active_model_sha)
    {
        if !ref_sha.is_empty() && ref_sha != cur_sha {
            let dto = DriftEvaluationDto {
                id: eval_id,
                reference_id: Some(ref_summary.id),
                evaluated_at,
                window_days,
                sample_count: obs_rows.len() as i64,
                status: "evaluation_error".to_string(),
                representative_status: ref_summary.representative_status,
                input_drift_detected: false,
                output_drift_detected: false,
                summary: format!(
                    "Referencia incompatible con el modelo activo (ref={} vs activo={}).",
                    &ref_sha[..ref_sha.len().min(12)],
                    &cur_sha[..cur_sha.len().min(12)]
                ),
                features: Vec::new(),
                warning_note: "No se comparan salidas entre modelos distintos sin referencia actualizada.".to_string(),
            };
            persist_drift_eval(pool, &dto).await?;
            return Ok(dto);
        }
    }

    let sample_count = obs_rows.len() as i64;
    if sample_count < ref_payload.min_observations {
        let dto = DriftEvaluationDto {
            id: eval_id,
            reference_id: Some(ref_summary.id),
            evaluated_at,
            window_days,
            sample_count,
            status: "insufficient_data".to_string(),
            representative_status: ref_summary.representative_status,
            input_drift_detected: false,
            output_drift_detected: false,
            summary: format!(
                "Datos insuficientes: {sample_count} archivos observados frente al mínimo configurado de {} archivos.",
                ref_payload.min_observations
            ),
            features: Vec::new(),
            warning_note: "La unidad de comparación es el archivo; las ventanas solapadas no se cuentan como observaciones independientes.".to_string(),
        };
        persist_drift_eval(pool, &dto).await?;
        return Ok(dto);
    }

    let mut features = Vec::new();
    let (mut input_alert, mut output_alert) = (false, false);

    for (name, spec) in &ref_payload.input_numeric {
        let m = evaluate_numeric_feature(name, "input_numeric", spec, &extract_numeric(&obs_rows, name));
        if m.alerted {
            input_alert = true;
        }
        features.push(m);
    }
    for (name, spec) in &ref_payload.input_categorical {
        let m = evaluate_categorical_feature(name, spec, &extract_categorical(&obs_rows, name));
        if m.alerted {
            input_alert = true;
        }
        features.push(m);
    }
    for (name, spec) in &ref_payload.output_numeric {
        let m = evaluate_numeric_feature(name, "output_numeric", spec, &extract_numeric(&obs_rows, name));
        if m.alerted {
            output_alert = true;
        }
        features.push(m);
    }

    let status = if input_alert || output_alert { "drift_detected" } else { "no_alert" };
    let summary = match (input_alert, output_alert) {
        (true, true) => format!("Cambio detectado en entradas y salidas sobre {sample_count} archivos."),
        (true, false) => format!("Cambio detectado en entradas sobre {sample_count} archivos; sin alerta en salidas."),
        (false, true) => format!("Cambio detectado en salidas sobre {sample_count} archivos; sin alerta en entradas."),
        (false, false) => format!("Sin alerta según criterio configurado sobre {sample_count} archivos ({}).", ref_summary.version),
    };

    let dto = DriftEvaluationDto {
        id: eval_id,
        reference_id: Some(ref_summary.id),
        evaluated_at,
        window_days,
        sample_count,
        status: status.to_string(),
        representative_status: ref_summary.representative_status,
        input_drift_detected: input_alert,
        output_drift_detected: output_alert,
        summary,
        features,
        warning_note: "Una alerta de drift inicia una investigación técnica; no demuestra pérdida automática de F1 ni concept drift, y no dispara reentrenamiento automático.".to_string(),
    };

    persist_drift_eval(pool, &dto).await?;
    Ok(dto)
}

pub async fn get_drift_status(pool: &SqlitePool) -> Result<DriftStatusResponseDto, ApiError> {
    let active_reference = sqlx::query_as::<_, DriftReferenceSummary>(
        r#"
        SELECT id, version, name, provenance, observation_unit, file_count, source_group_count,
               representative_status, extraction_version, model_sha256, contract_version,
               contract_sha256, min_observations, is_active, created_at
        FROM drift_references WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1
        "#,
    )
    .fetch_optional(pool)
    .await?;

    let eval_rows = sqlx::query_as::<_, DriftEvalDbRow>(
        "SELECT * FROM drift_evaluations ORDER BY evaluated_at DESC LIMIT 10",
    )
    .fetch_all(pool)
    .await?;

    let evals: Vec<DriftEvaluationDto> = eval_rows
        .into_iter()
        .map(|row| {
            serde_json::from_str::<DriftEvaluationDto>(&row.details_json).unwrap_or(
                DriftEvaluationDto {
                    id: row.id,
                    reference_id: row.reference_id,
                    evaluated_at: row.evaluated_at,
                    window_days: row.window_days,
                    sample_count: row.sample_count,
                    status: row.status,
                    representative_status: row.representative_status,
                    input_drift_detected: row.input_drift_detected != 0,
                    output_drift_detected: row.output_drift_detected != 0,
                    summary: row.summary,
                    features: Vec::new(),
                    warning_note: String::new(),
                },
            )
        })
        .collect();

    let representative_status = active_reference
        .as_ref()
        .map(|r| r.representative_status.clone())
        .unwrap_or_else(|| "pending_representative_corpus".to_string());
    let latest_evaluation = evals.first().cloned();

    Ok(DriftStatusResponseDto {
        active_reference,
        representative_status,
        latest_evaluation,
        recent_evaluations: evals,
    })
}

fn extract_numeric(rows: &[DriftObservationRow], name: &str) -> Vec<f64> {
    rows.iter()
        .filter_map(|r| match name {
            "duration_seconds" => r.duration_seconds,
            "peak_before_normalization" => r.peak_before_normalization,
            "rms_before_normalization" => r.rms_before_normalization,
            "silence_ratio" => r.silence_ratio,
            "clipping_ratio" => r.clipping_ratio,
            "logmel_mean" => r.logmel_mean,
            "logmel_std" => r.logmel_std,
            "spectral_centroid_hz" => r.spectral_centroid_hz,
            "positive_window_ratio" => r.positive_window_ratio,
            "score_mean" => r.score_mean,
            "score_max" => r.score_max,
            _ => None,
        })
        .filter(|v| v.is_finite())
        .collect()
}

fn extract_categorical(rows: &[DriftObservationRow], name: &str) -> Vec<String> {
    rows.iter()
        .filter_map(|r| match name {
            "original_sample_rate" => r.original_sample_rate.map(|v| v.to_string()),
            "original_channels" => r.original_channels.map(|v| v.to_string()),
            "short_clip" => Some(if r.short_clip != 0 { "short_clip" } else { "full" }.to_string()),
            "downmix_cancellation" => Some(
                if r.downmix_cancellation_candidate != 0 { "candidate" } else { "normal" }.to_string(),
            ),
            _ => None,
        })
        .collect()
}

fn evaluate_numeric_feature(
    name: &str,
    group: &str,
    spec: &NumericReferenceFeature,
    obs: &[f64],
) -> FeatureDriftMetric {
    if !spec.comparable {
        return FeatureDriftMetric {
            feature: name.to_string(),
            group: group.to_string(),
            unit: spec.unit.clone(),
            method: "wasserstein_1d_normalized".to_string(),
            n_ref: spec.samples.len(),
            n_obs: obs.len(),
            statistic: None,
            normalized_statistic: None,
            threshold: spec.threshold_normalized_w1,
            ref_mean: summarize_f64(&spec.samples).0,
            obs_mean: summarize_f64(obs).0,
            alerted: false,
            status: "incompatible".to_string(),
            note: spec.note.clone(),
        };
    }
    if spec.samples.is_empty() || obs.is_empty() {
        return FeatureDriftMetric {
            feature: name.to_string(),
            group: group.to_string(),
            unit: spec.unit.clone(),
            method: "wasserstein_1d_normalized".to_string(),
            n_ref: spec.samples.len(),
            n_obs: obs.len(),
            statistic: None,
            normalized_statistic: None,
            threshold: spec.threshold_normalized_w1,
            ref_mean: summarize_f64(&spec.samples).0,
            obs_mean: summarize_f64(obs).0,
            alerted: false,
            status: "constant_or_skipped".to_string(),
            note: Some("Valores ausentes en referencia o muestra observada.".to_string()),
        };
    }
    let raw_w1 = wasserstein_1d(&spec.samples, obs).unwrap_or(0.0);
    let norm_w1 = raw_w1 / if spec.scale > 1e-9 { spec.scale } else { 1.0 };
    let alerted = norm_w1 > spec.threshold_normalized_w1;
    FeatureDriftMetric {
        feature: name.to_string(),
        group: group.to_string(),
        unit: spec.unit.clone(),
        method: "wasserstein_1d_normalized".to_string(),
        n_ref: spec.samples.len(),
        n_obs: obs.len(),
        statistic: Some(raw_w1),
        normalized_statistic: Some(norm_w1),
        threshold: spec.threshold_normalized_w1,
        ref_mean: summarize_f64(&spec.samples).0,
        obs_mean: summarize_f64(obs).0,
        alerted,
        status: if alerted { "alert" } else { "ok" }.to_string(),
        note: spec.note.clone(),
    }
}

fn evaluate_categorical_feature(
    name: &str,
    spec: &CategoricalReferenceFeature,
    obs: &[String],
) -> FeatureDriftMetric {
    if !spec.comparable || obs.is_empty() {
        return FeatureDriftMetric {
            feature: name.to_string(),
            group: "input_categorical".to_string(),
            unit: "proportion".to_string(),
            method: "max_abs_proportion_shift".to_string(),
            n_ref: spec.proportions.len(),
            n_obs: obs.len(),
            statistic: None,
            normalized_statistic: None,
            threshold: spec.threshold_max_abs_diff,
            ref_mean: None,
            obs_mean: None,
            alerted: false,
            status: if !spec.comparable { "incompatible" } else { "constant_or_skipped" }.to_string(),
            note: spec.note.clone(),
        };
    }
    let mut counts: HashMap<&str, usize> = HashMap::new();
    for v in obs {
        *counts.entry(v.as_str()).or_insert(0) += 1;
    }
    let total = obs.len() as f64;
    let mut max_diff = 0.0_f64;
    for k in spec.proportions.keys().map(String::as_str).chain(counts.keys().copied()) {
        let p_ref = spec.proportions.get(k).copied().unwrap_or(0.0);
        let p_obs = counts.get(k).copied().unwrap_or(0) as f64 / total;
        max_diff = max_diff.max((p_obs - p_ref).abs());
    }
    let alerted = max_diff > spec.threshold_max_abs_diff;
    FeatureDriftMetric {
        feature: name.to_string(),
        group: "input_categorical".to_string(),
        unit: "proportion".to_string(),
        method: "max_abs_proportion_shift".to_string(),
        n_ref: spec.proportions.len(),
        n_obs: obs.len(),
        statistic: Some(max_diff),
        normalized_statistic: Some(max_diff),
        threshold: spec.threshold_max_abs_diff,
        ref_mean: None,
        obs_mean: None,
        alerted,
        status: if alerted { "alert" } else { "ok" }.to_string(),
        note: spec.note.clone(),
    }
}

async fn persist_drift_eval(pool: &SqlitePool, dto: &DriftEvaluationDto) -> Result<(), ApiError> {
    let details_json = serde_json::to_string(dto)
        .map_err(|e| ApiError::Internal(format!("error serializando evaluación drift: {e}")))?;
    sqlx::query(
        r#"
        INSERT INTO drift_evaluations (
            id, reference_id, evaluated_at, window_days, sample_count, status,
            representative_status, input_drift_detected, output_drift_detected,
            summary, details_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(&dto.id)
    .bind(&dto.reference_id)
    .bind(&dto.evaluated_at)
    .bind(dto.window_days)
    .bind(dto.sample_count)
    .bind(&dto.status)
    .bind(&dto.representative_status)
    .bind(if dto.input_drift_detected { 1_i64 } else { 0_i64 })
    .bind(if dto.output_drift_detected { 1_i64 } else { 0_i64 })
    .bind(&dto.summary)
    .bind(&details_json)
    .execute(pool)
    .await?;
    Ok(())
}
