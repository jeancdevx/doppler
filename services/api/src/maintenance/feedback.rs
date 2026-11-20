use std::collections::HashMap;

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{FromRow, SqlitePool};

use crate::domain::generate_opaque_id;
use crate::error::ApiError;

#[derive(Debug, Deserialize)]
pub struct CreateFeedbackRequest {
    pub feedback_type: String,
    pub window_index: Option<i64>,
    pub comment: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateFeedbackRequest {
    pub review_status: String,
    pub verified_label: Option<String>,
    pub resolution_note: Option<String>,
}

#[derive(Debug, Clone, FromRow)]
struct FeedbackDbRow {
    id: String,
    session_id: String,
    job_id: String,
    window_index: Option<i64>,
    feedback_type: String,
    comment: Option<String>,
    displayed_label: Option<String>,
    displayed_score: Option<f64>,
    displayed_threshold: Option<f64>,
    window_start_seconds: Option<f64>,
    window_end_seconds: Option<f64>,
    model_sha256: Option<String>,
    contract_version: Option<String>,
    contract_sha256: Option<String>,
    audio_available_at_report: i64,
    audio_expires_at: Option<String>,
    review_status: String,
    verified_label: Option<String>,
    resolution_note: Option<String>,
    created_at: String,
    updated_at: String,
    reviewed_at: Option<String>,
    resolved_at: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FeedbackReportDto {
    pub id: String,
    pub job_id: String,
    pub window_index: Option<i64>,
    pub feedback_type: String,
    pub comment: Option<String>,
    pub displayed_label: Option<String>,
    pub displayed_score: Option<f64>,
    pub displayed_threshold: Option<f64>,
    pub window_start_seconds: Option<f64>,
    pub window_end_seconds: Option<f64>,
    pub model_sha256: Option<String>,
    pub contract_version: Option<String>,
    pub contract_sha256: Option<String>,
    pub audio_available_at_report: bool,
    pub audio_currently_available: bool,
    pub audio_expires_at: Option<String>,
    pub review_status: String,
    pub verified_label: Option<String>,
    pub resolution_note: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub reviewed_at: Option<String>,
    pub resolved_at: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FeedbackMetricsSummaryDto {
    pub status: &'static str,
    pub total_reports: usize,
    pub deduplicated_verified_windows: usize,
    pub excluded_uncertain_or_general: usize,
    pub confirmed_emergency: usize,
    pub confirmed_non_emergency: usize,
    pub agreement_rate_on_verified_sample: Option<f64>,
    pub methodology_note: &'static str,
}

#[derive(Debug, Clone, Serialize)]
pub struct AdminFeedbackListDto {
    pub reports: Vec<FeedbackReportDto>,
    pub metrics: FeedbackMetricsSummaryDto,
}

pub fn valid_feedback_type(s: &str) -> bool {
    matches!(
        s,
        "false_alarm" | "missed_emergency" | "technical_issue" | "uncertain_or_other"
    )
}

pub fn valid_review_transition(from: &str, to: &str) -> bool {
    matches!(
        (from, to),
        ("received", "in_review")
            | ("in_review", "confirmed")
            | ("in_review", "dismissed")
            | ("in_review", "insufficient_evidence")
            | ("confirmed", "resolved")
            | ("dismissed", "resolved")
            | ("insufficient_evidence", "resolved")
    )
}

pub async fn create_feedback_report(
    pool: &SqlitePool,
    session_id: &str,
    job_id: &str,
    req: &CreateFeedbackRequest,
    rate_limit_per_hour: i64,
) -> Result<FeedbackReportDto, ApiError> {
    if !valid_feedback_type(&req.feedback_type) {
        return Err(ApiError::Validation(
            "Tipo de reporte inválido. Usa: false_alarm, missed_emergency, technical_issue o uncertain_or_other."
                .to_string(),
        ));
    }

    let cleaned_comment = req
        .comment
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty());
    if let Some(c) = cleaned_comment {
        if c.chars().count() > 1000 {
            return Err(ApiError::Validation(
                "El comentario no puede superar los 1000 caracteres.".to_string(),
            ));
        }
    }

    let since = (Utc::now() - Duration::hours(1)).to_rfc3339();
    let (recent_count,): (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM feedback_reports WHERE session_id = ? AND created_at >= ?",
    )
    .bind(session_id)
    .bind(&since)
    .fetch_one(pool)
    .await?;
    if recent_count >= rate_limit_per_hour {
        return Err(ApiError::RateLimited(
            "Se alcanzó el límite temporal de reportes de retroalimentación para esta sesión."
                .to_string(),
        ));
    }

    let job_row: Option<(String, Option<String>, Option<String>, Option<String>, Option<f64>, String)> =
        sqlx::query_as(
            r#"
            SELECT status, model_sha256, contract_version, contract_sha256, threshold, expires_at
            FROM jobs WHERE id = ? AND session_id = ? AND deleted_at IS NULL
            "#,
        )
        .bind(job_id)
        .bind(session_id)
        .fetch_optional(pool)
        .await?;

    let Some((status, model_sha, contract_ver, contract_sha, threshold, expires_at)) = job_row
    else {
        return Err(ApiError::NotFound(
            "Trabajo no encontrado en esta sesión.".to_string(),
        ));
    };

    if matches!(req.feedback_type.as_str(), "false_alarm" | "missed_emergency")
        && req.window_index.is_none()
    {
        return Err(ApiError::Validation(
            "Para reportar una posible falsa alarma o emergencia no detectada debes seleccionar una ventana concreta; los comentarios generales no equivalen a una etiqueta global."
                .to_string(),
        ));
    }

    let (disp_label, disp_score, win_start, win_end) = if let Some(w_idx) = req.window_index {
        let win_row: Option<(f64, f64, f64, String)> = sqlx::query_as(
            "SELECT start_seconds, end_seconds, score, label FROM job_windows WHERE job_id = ? AND window_index = ?",
        )
        .bind(job_id)
        .bind(w_idx)
        .fetch_optional(pool)
        .await?;

        let Some((s, e, sc, lb)) = win_row else {
            return Err(ApiError::NotFound(
                "La ventana indicada no existe en este trabajo.".to_string(),
            ));
        };
        (Some(lb), Some(sc), Some(s), Some(e))
    } else {
        (None, None, None, None)
    };

    let audio_available_now = status != "uploading" && is_not_expired(&expires_at);
    let report_id = format!("fb_{}", generate_opaque_id(10));
    let now = Utc::now().to_rfc3339();

    let mut tx = pool.begin().await?;
    sqlx::query(
        r#"
        INSERT INTO feedback_reports (
            id, session_id, job_id, window_index, feedback_type, comment,
            displayed_label, displayed_score, displayed_threshold,
            window_start_seconds, window_end_seconds,
            model_sha256, contract_version, contract_sha256,
            audio_available_at_report, audio_expires_at,
            review_status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'received', ?, ?)
        "#,
    )
    .bind(&report_id)
    .bind(session_id)
    .bind(job_id)
    .bind(req.window_index)
    .bind(&req.feedback_type)
    .bind(cleaned_comment)
    .bind(&disp_label)
    .bind(disp_score)
    .bind(threshold)
    .bind(win_start)
    .bind(win_end)
    .bind(&model_sha)
    .bind(&contract_ver)
    .bind(&contract_sha)
    .bind(if audio_available_now { 1_i64 } else { 0_i64 })
    .bind(&expires_at)
    .bind(&now)
    .bind(&now)
    .execute(&mut *tx)
    .await?;

    sqlx::query(
        "INSERT INTO feedback_events (report_id, from_status, to_status, actor, note, created_at) VALUES (?, NULL, 'received', 'user_session', 'Reporte creado por propietario de sesión', ?)",
    )
    .bind(&report_id)
    .bind(&now)
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;

    Ok(FeedbackReportDto {
        id: report_id,
        job_id: job_id.to_string(),
        window_index: req.window_index,
        feedback_type: req.feedback_type.clone(),
        comment: cleaned_comment.map(str::to_string),
        displayed_label: disp_label,
        displayed_score: disp_score,
        displayed_threshold: threshold,
        window_start_seconds: win_start,
        window_end_seconds: win_end,
        model_sha256: model_sha,
        contract_version: contract_ver,
        contract_sha256: contract_sha,
        audio_available_at_report: audio_available_now,
        audio_currently_available: audio_available_now,
        audio_expires_at: Some(expires_at),
        review_status: "received".to_string(),
        verified_label: None,
        resolution_note: None,
        created_at: now.clone(),
        updated_at: now,
        reviewed_at: None,
        resolved_at: None,
    })
}

pub async fn list_feedback_for_session_job(
    pool: &SqlitePool,
    session_id: &str,
    job_id: &str,
) -> Result<Vec<FeedbackReportDto>, ApiError> {
    let job_exists: Option<(String,)> = sqlx::query_as(
        "SELECT expires_at FROM jobs WHERE id = ? AND session_id = ? AND deleted_at IS NULL",
    )
    .bind(job_id)
    .bind(session_id)
    .fetch_optional(pool)
    .await?;

    let rows = sqlx::query_as::<_, FeedbackDbRow>(
        "SELECT * FROM feedback_reports WHERE session_id = ? AND job_id = ? ORDER BY created_at DESC",
    )
    .bind(session_id)
    .bind(job_id)
    .fetch_all(pool)
    .await?;

    if job_exists.is_none() && rows.is_empty() {
        return Err(ApiError::NotFound(
            "Trabajo no encontrado en esta sesión.".to_string(),
        ));
    }

    let audio_live = job_exists
        .as_ref()
        .map(|(exp,)| is_not_expired(exp))
        .unwrap_or(false);

    Ok(rows
        .into_iter()
        .map(|r| db_row_to_feedback_dto(r, audio_live))
        .collect())
}

pub async fn list_all_feedback_admin(
    pool: &SqlitePool,
    status_filter: Option<&str>,
) -> Result<AdminFeedbackListDto, ApiError> {
    let rows = if let Some(st) = status_filter.filter(|s| !s.is_empty() && *s != "all") {
        sqlx::query_as::<_, FeedbackDbRow>(
            "SELECT * FROM feedback_reports WHERE review_status = ? ORDER BY created_at DESC LIMIT 200",
        )
        .bind(st)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query_as::<_, FeedbackDbRow>(
            "SELECT * FROM feedback_reports ORDER BY created_at DESC LIMIT 200",
        )
        .fetch_all(pool)
        .await?
    };

    let active_job_rows: Vec<(String, String)> = sqlx::query_as(
        "SELECT id, expires_at FROM jobs WHERE deleted_at IS NULL AND status != 'uploading'",
    )
    .fetch_all(pool)
    .await?;
    let active_map: HashMap<String, bool> = active_job_rows
        .into_iter()
        .map(|(id, exp)| (id, is_not_expired(&exp)))
        .collect();

    let reports: Vec<FeedbackReportDto> = rows
        .into_iter()
        .map(|r| {
            let live = active_map.get(&r.job_id).copied().unwrap_or(false);
            db_row_to_feedback_dto(r, live)
        })
        .collect();

    let metrics = compute_reviewed_feedback_metrics(&reports);
    Ok(AdminFeedbackListDto { reports, metrics })
}

pub async fn update_feedback_review_admin(
    pool: &SqlitePool,
    report_id: &str,
    req: &UpdateFeedbackRequest,
) -> Result<FeedbackReportDto, ApiError> {
    let Some(existing) =
        sqlx::query_as::<_, FeedbackDbRow>("SELECT * FROM feedback_reports WHERE id = ?")
            .bind(report_id)
            .fetch_optional(pool)
            .await?
    else {
        return Err(ApiError::NotFound(
            "Reporte de retroalimentación no encontrado.".to_string(),
        ));
    };

    if !valid_review_transition(&existing.review_status, &req.review_status) {
        return Err(ApiError::Conflict(format!(
            "Transición de revisión inválida: '{}' → '{}'. Secuencia permitida: received → in_review → confirmed|dismissed|insufficient_evidence → resolved.",
            existing.review_status, req.review_status
        )));
    }

    if let Some(ref lbl) = req.verified_label {
        if !matches!(lbl.as_str(), "EMERGENCY" | "NON_EMERGENCY" | "UNCERTAIN") {
            return Err(ApiError::Validation(
                "verified_label debe ser EMERGENCY, NON_EMERGENCY o UNCERTAIN.".to_string(),
            ));
        }
        if existing.window_index.is_none() {
            return Err(ApiError::Validation(
                "No se puede asignar etiqueta verificada de clase a un reporte general sin ventana asociada."
                    .to_string(),
            ));
        }
    }

    let cleaned_note = req
        .resolution_note
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty());
    let now = Utc::now().to_rfc3339();
    let reviewed_at = if matches!(
        req.review_status.as_str(),
        "in_review" | "confirmed" | "dismissed" | "insufficient_evidence"
    ) {
        Some(now.clone())
    } else {
        existing.reviewed_at.clone()
    };
    let resolved_at = if req.review_status == "resolved" {
        Some(now.clone())
    } else {
        existing.resolved_at.clone()
    };
    let final_verified_label = req.verified_label.clone().or(existing.verified_label.clone());
    let final_note = cleaned_note
        .map(str::to_string)
        .or(existing.resolution_note.clone());

    let mut tx = pool.begin().await?;
    sqlx::query(
        r#"
        UPDATE feedback_reports
        SET review_status = ?, verified_label = ?, resolution_note = ?,
            updated_at = ?, reviewed_at = ?, resolved_at = ?
        WHERE id = ?
        "#,
    )
    .bind(&req.review_status)
    .bind(&final_verified_label)
    .bind(&final_note)
    .bind(&now)
    .bind(&reviewed_at)
    .bind(&resolved_at)
    .bind(report_id)
    .execute(&mut *tx)
    .await?;

    sqlx::query(
        "INSERT INTO feedback_events (report_id, from_status, to_status, actor, note, created_at) VALUES (?, ?, ?, 'admin', ?, ?)",
    )
    .bind(report_id)
    .bind(&existing.review_status)
    .bind(&req.review_status)
    .bind(cleaned_note)
    .bind(&now)
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;

    let updated = sqlx::query_as::<_, FeedbackDbRow>("SELECT * FROM feedback_reports WHERE id = ?")
        .bind(report_id)
        .fetch_one(pool)
        .await?;

    let audio_live = sqlx::query_as::<_, (String,)>(
        "SELECT expires_at FROM jobs WHERE id = ? AND deleted_at IS NULL AND status != 'uploading'",
    )
    .bind(&updated.job_id)
    .fetch_optional(pool)
    .await?
    .map(|(exp,)| is_not_expired(&exp))
    .unwrap_or(false);

    Ok(db_row_to_feedback_dto(updated, audio_live))
}

pub fn compute_reviewed_feedback_metrics(reports: &[FeedbackReportDto]) -> FeedbackMetricsSummaryDto {
    let mut dedup: HashMap<(String, i64, String), &FeedbackReportDto> = HashMap::new();
    let mut excluded = 0usize;

    for r in reports {
        let Some(w_idx) = r.window_index else {
            excluded += 1;
            continue;
        };
        let Some(ref v_lbl) = r.verified_label else {
            excluded += 1;
            continue;
        };
        if v_lbl == "UNCERTAIN" {
            excluded += 1;
            continue;
        }
        let key = (
            r.job_id.clone(),
            w_idx,
            r.model_sha256.clone().unwrap_or_default(),
        );
        dedup.entry(key).or_insert(r);
    }

    if dedup.is_empty() {
        return FeedbackMetricsSummaryDto {
            status: "unavailable",
            total_reports: reports.len(),
            deduplicated_verified_windows: 0,
            excluded_uncertain_or_general: excluded,
            confirmed_emergency: 0,
            confirmed_non_emergency: 0,
            agreement_rate_on_verified_sample: None,
            methodology_note: "Métricas predictivas no disponibles: no existen ventanas con etiqueta verificada tras deduplicación y exclusión de casos inciertos.",
        };
    }

    let (mut em, mut non_em, mut matches) = (0usize, 0usize, 0usize);
    for r in dedup.values() {
        if let Some(ref v) = r.verified_label {
            if v == "EMERGENCY" { em += 1; } else { non_em += 1; }
            if r.displayed_label.as_deref() == Some(v.as_str()) { matches += 1; }
        }
    }
    let n = dedup.len();
    FeedbackMetricsSummaryDto {
        status: "available_biased_sample",
        total_reports: reports.len(),
        deduplicated_verified_windows: n,
        excluded_uncertain_or_general: excluded,
        confirmed_emergency: em,
        confirmed_non_emergency: non_em,
        agreement_rate_on_verified_sample: Some(matches as f64 / n as f64),
        methodology_note: "Muestra sesgada por reporte voluntario (no representa necesariamente todo el tráfico). Deduplicada por (job_id, window_index, model_sha256), excluyendo etiquetas inciertas y comentarios generales.",
    }
}

fn db_row_to_feedback_dto(r: FeedbackDbRow, audio_live: bool) -> FeedbackReportDto {
    let _ = r.session_id;
    FeedbackReportDto {
        id: r.id,
        job_id: r.job_id,
        window_index: r.window_index,
        feedback_type: r.feedback_type,
        comment: r.comment,
        displayed_label: r.displayed_label,
        displayed_score: r.displayed_score,
        displayed_threshold: r.displayed_threshold,
        window_start_seconds: r.window_start_seconds,
        window_end_seconds: r.window_end_seconds,
        model_sha256: r.model_sha256,
        contract_version: r.contract_version,
        contract_sha256: r.contract_sha256,
        audio_available_at_report: r.audio_available_at_report != 0,
        audio_currently_available: audio_live,
        audio_expires_at: r.audio_expires_at,
        review_status: r.review_status,
        verified_label: r.verified_label,
        resolution_note: r.resolution_note,
        created_at: r.created_at,
        updated_at: r.updated_at,
        reviewed_at: r.reviewed_at,
        resolved_at: r.resolved_at,
    }
}

fn is_not_expired(expires_at: &str) -> bool {
    DateTime::parse_from_rfc3339(expires_at)
        .map(|dt| dt.with_timezone(&Utc) > Utc::now())
        .unwrap_or(false)
}
