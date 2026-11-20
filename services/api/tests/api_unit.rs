use std::collections::BTreeMap;

use sqlx::sqlite::SqlitePoolOptions;

use doppler_api::db;
use doppler_api::domain::{
    merge_positive_intervals, sanitize_filename, sign_session_token, verify_session_token,
    WindowDto,
};
use doppler_api::inference::{
    InferenceAudioMetadata, InferenceObservationalStats, InferenceResult, InferenceTimings,
    InferenceWindow,
};
use doppler_api::maintenance::{
    self, CategoricalReferenceFeature, CreateFeedbackRequest, DriftReferencePayload,
    FeedbackReportDto, NumericReferenceFeature, UpdateFeedbackRequest,
};

#[test]
fn session_token_sign_and_verify_roundtrip() {
    let secret = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    let session_id = "a1b2c3d4e5f60718293a4b5c6d7e8f90";
    let signed = sign_session_token(session_id, secret);
    assert_eq!(
        verify_session_token(&signed, secret),
        Some(session_id.to_string())
    );
    assert_eq!(
        verify_session_token(&signed, "wrong_secret_0123456789abcdef0123"),
        None
    );
    assert_eq!(verify_session_token("tampered.deadbeef", secret), None);
}

#[test]
fn filename_sanitization_strips_paths_and_controls() {
    assert_eq!(sanitize_filename("../../etc/passwd.wav"), "passwd.wav");
    assert_eq!(
        sanitize_filename("C:\\fakepath\\sirena\x00test.wav"),
        "sirenatest.wav"
    );
    assert_eq!(sanitize_filename("   "), "audio.wav");
}

#[test]
fn merge_positive_intervals_merges_overlapping_windows_accurately() {
    let windows = vec![
        WindowDto {
            index: 0,
            start_seconds: 0.0,
            end_seconds: 3.0,
            score: 0.2,
            label: "NON_EMERGENCY".into(),
            margin_vs_threshold: -0.45,
        },
        WindowDto {
            index: 1,
            start_seconds: 1.5,
            end_seconds: 4.5,
            score: 0.82,
            label: "EMERGENCY".into(),
            margin_vs_threshold: 0.16,
        },
        WindowDto {
            index: 2,
            start_seconds: 3.0,
            end_seconds: 6.0,
            score: 0.91,
            label: "EMERGENCY".into(),
            margin_vs_threshold: 0.25,
        },
        WindowDto {
            index: 3,
            start_seconds: 7.5,
            end_seconds: 10.5,
            score: 0.71,
            label: "EMERGENCY".into(),
            margin_vs_threshold: 0.05,
        },
    ];

    let (merged, coverage) = merge_positive_intervals(&windows);
    assert_eq!(merged.len(), 2);
    assert!((merged[0].start_seconds - 1.5).abs() < 1e-6);
    assert!((merged[0].end_seconds - 6.0).abs() < 1e-6);
    assert_eq!(merged[0].window_count, 2);
    assert!((merged[0].max_score - 0.91).abs() < 1e-6);
    assert!((merged[1].start_seconds - 7.5).abs() < 1e-6);
    assert!((merged[1].end_seconds - 10.5).abs() < 1e-6);
    assert!((coverage - 7.5).abs() < 1e-6);
}

#[test]
fn admin_token_constant_time_verification() {
    let configured = Some("super_secret_admin_token_for_unit_test_123456");
    assert!(maintenance::verify_admin_token(configured, configured).is_ok());
    assert!(maintenance::verify_admin_token(Some("wrong_token"), configured).is_err());
    assert!(maintenance::verify_admin_token(None, configured).is_err());
    assert!(maintenance::verify_admin_token(configured, None).is_err());
}

#[test]
fn wasserstein_1d_matches_exact_shift_and_zero_on_identical() {
    let base = vec![1.0, 2.0, 3.0, 4.0];
    let same = vec![4.0, 1.0, 3.0, 2.0];
    let shifted = vec![3.0, 4.0, 5.0, 6.0];

    let d0 = maintenance::wasserstein_1d(&base, &same).unwrap();
    let d2 = maintenance::wasserstein_1d(&base, &shifted).unwrap();
    assert!(d0.abs() < 1e-9);
    assert!((d2 - 2.0).abs() < 1e-9);
}

#[test]
fn feedback_review_state_machine_enforces_allowed_transitions() {
    assert!(maintenance::valid_review_transition("received", "in_review"));
    assert!(maintenance::valid_review_transition("in_review", "confirmed"));
    assert!(maintenance::valid_review_transition("in_review", "dismissed"));
    assert!(maintenance::valid_review_transition(
        "in_review",
        "insufficient_evidence"
    ));
    assert!(maintenance::valid_review_transition("confirmed", "resolved"));
    assert!(maintenance::valid_review_transition(
        "insufficient_evidence",
        "resolved"
    ));

    // Saltos no permitidos
    assert!(!maintenance::valid_review_transition("received", "confirmed"));
    assert!(!maintenance::valid_review_transition("received", "resolved"));
    assert!(!maintenance::valid_review_transition("resolved", "in_review"));
}

#[test]
fn feedback_metrics_deduplicates_and_excludes_uncertain_or_general() {
    let mk = |id: &str, job: &str, win: Option<i64>, disp: Option<&str>, ver: Option<&str>| {
        FeedbackReportDto {
            id: id.into(),
            job_id: job.into(),
            window_index: win,
            feedback_type: "false_alarm".into(),
            comment: None,
            displayed_label: disp.map(str::to_string),
            displayed_score: Some(0.8),
            displayed_threshold: Some(0.6547843813896179),
            window_start_seconds: Some(0.0),
            window_end_seconds: Some(3.0),
            model_sha256: Some("sha_v1".into()),
            contract_version: Some("1.0.0".into()),
            contract_sha256: Some("csha_v1".into()),
            audio_available_at_report: true,
            audio_currently_available: true,
            audio_expires_at: None,
            review_status: "confirmed".into(),
            verified_label: ver.map(str::to_string),
            resolution_note: None,
            created_at: "2026-11-20T00:00:00Z".into(),
            updated_at: "2026-11-20T00:00:00Z".into(),
            reviewed_at: None,
            resolved_at: None,
        }
    };

    // Sin etiquetas verificadas -> unavailable
    let empty_m = maintenance::compute_reviewed_feedback_metrics(&[mk(
        "fb1",
        "j1",
        Some(0),
        Some("EMERGENCY"),
        None,
    )]);
    assert_eq!(empty_m.status, "unavailable");
    assert_eq!(empty_m.deduplicated_verified_windows, 0);

    // Con duplicado en misma (job, window, model), un UNCERTAIN y un general (None)
    let reports = vec![
        mk("fb1", "j1", Some(0), Some("EMERGENCY"), Some("NON_EMERGENCY")),
        mk("fb2", "j1", Some(0), Some("EMERGENCY"), Some("EMERGENCY")), // duplicado más antiguo
        mk("fb3", "j1", Some(1), Some("EMERGENCY"), Some("UNCERTAIN")), // excluido
        mk("fb4", "j1", None, None, Some("EMERGENCY")),                 // comentario general excluido
        mk("fb5", "j2", Some(0), Some("EMERGENCY"), Some("EMERGENCY")),
    ];
    let m = maintenance::compute_reviewed_feedback_metrics(&reports);
    assert_eq!(m.status, "available_biased_sample");
    assert_eq!(m.deduplicated_verified_windows, 2);
    assert_eq!(m.confirmed_emergency, 1);
    assert_eq!(m.confirmed_non_emergency, 1);
    assert!((m.agreement_rate_on_verified_sample.unwrap() - 0.5).abs() < 1e-9);
}

fn sample_inference_result(score: f64, sr: i64, duration: f64) -> InferenceResult {
    let threshold = 0.6547843813896179;
    let is_em = score >= threshold;
    InferenceResult {
        audio_sha256: "deadbeef01".into(),
        model_sha256: "e0dc2eaa1415f66d7442a8db7cf249129520ece20d575df35dc0aefb29f89d2a".into(),
        contract_version: "1.0.0".into(),
        contract_sha256: "02b2a9884628a391cedfbf36803a775f85357fed05fb2549e3c01da157736557".into(),
        threshold,
        score_type: "sigmoid_probability_not_calibrated".into(),
        audio: InferenceAudioMetadata {
            original_sample_rate: sr,
            original_channels: 1,
            prepared_sample_rate: 16000,
            prepared_channels: 1,
            duration_seconds: duration,
            prepared_samples: (duration * 16000.0) as i64,
            peak_before_normalization: 0.72,
            peak_after_normalization: 0.99,
            rms_after_normalization: 0.28,
            downmix_cancellation_candidate: false,
            discarded_tail_samples: 0,
            discarded_tail_seconds: 0.0,
            window_seconds: 3.0,
            hop_seconds: 1.5,
            observational: Some(InferenceObservationalStats {
                extraction_version: "obs_v1".into(),
                rms_before_normalization: 0.21,
                silence_ratio: 0.04,
                clipping_ratio: 0.0,
                logmel_mean: Some(-34.5),
                logmel_std: Some(12.2),
                spectral_centroid_hz: Some(1250.0),
            }),
        },
        windows: vec![InferenceWindow {
            index: 0,
            start_seconds: 0.0,
            end_seconds: 3.0,
            score,
            label: if is_em { "EMERGENCY" } else { "NON_EMERGENCY" }.into(),
            margin_vs_threshold: score - threshold,
        }],
        windows_total: 1,
        windows_positive: if is_em { 1 } else { 0 },
        timings: InferenceTimings {
            decode_and_prepare_ms: 8.5,
            inference_ms: 21.3,
            total_ms: 29.8,
        },
        short_clip: false,
        short_clip_message: None,
    }
}

#[tokio::test]
async fn sqlite_telemetry_survives_24h_deletion_avoids_duplicates_and_evaluates_drift() {
    let pool = SqlitePoolOptions::new()
        .max_connections(1)
        .connect("sqlite::memory:")
        .await
        .unwrap();
    sqlx::migrate!("./migrations").run(&pool).await.unwrap();

    db::ensure_session(&pool, "sess_a_1234567890").await.unwrap();
    db::ensure_session(&pool, "sess_b_1234567890").await.unwrap();

    // 1. Sin referencia -> status no_reference
    let e0 = maintenance::evaluate_drift_and_store(&pool, 30, None)
        .await
        .unwrap();
    assert_eq!(e0.status, "no_reference");
    assert_eq!(e0.representative_status, "pending_representative_corpus");

    // 2. Crear trabajo, completarlo, reintentar registro (sin duplicar), luego borrar trabajo 24 h
    db::create_uploading_job(
        &pool,
        "job_01",
        "run_01",
        "sess_a_1234567890",
        "privado_usuario.wav",
        "audio/wav",
        96000,
        "doppler/uploads/sess_a_1234567890/job_01.wav",
        24,
    )
    .await
    .unwrap();
    let res = sample_inference_result(0.92, 16000, 6.0);
    db::complete_job_with_result(&pool, "job_01", &res, 45.0, 2.0, 75.0)
        .await
        .unwrap();
    // Reintento idempotente: no debe duplicar fila en job_telemetry_history
    maintenance::record_completed_job_telemetry(&pool, "job_01", &res, 45.0, 2.0, 3.0, 80.0)
        .await
        .unwrap();

    // Crear feedback sobre ventana 0 por propietario (ok), rechazar sesión ajena (404)
    let fb = maintenance::create_feedback_report(
        &pool,
        "sess_a_1234567890",
        "job_01",
        &CreateFeedbackRequest {
            feedback_type: "false_alarm".into(),
            window_index: Some(0),
            comment: Some("Prueba unitaria controlada".into()),
        },
        30,
    )
    .await
    .unwrap();
    assert_eq!(fb.review_status, "received");

    let cross_err = maintenance::create_feedback_report(
        &pool,
        "sess_b_1234567890",
        "job_01",
        &CreateFeedbackRequest {
            feedback_type: "technical_issue".into(),
            window_index: None,
            comment: None,
        },
        30,
    )
    .await;
    assert!(cross_err.is_err());

    // Borrar trabajo (simulando retención 24 h)
    db::hard_delete_job(&pool, "job_01").await.unwrap();

    // La telemetría histórica sigue presente y sin duplicados (1 fila)
    let (tel_count,): (i64,) =
        sqlx::query_as("SELECT COUNT(*) FROM job_telemetry_history WHERE job_id = 'job_01'")
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(tel_count, 1);

    // El reporte refleja ahora audio_currently_available = false tras vencer/borrar el trabajo
    let admin_fb = maintenance::list_all_feedback_admin(&pool, None)
        .await
        .unwrap();
    assert_eq!(admin_fb.reports.len(), 1);
    assert!(!admin_fb.reports[0].audio_currently_available);

    // Transición válida received -> in_review -> insufficient_evidence -> resolved
    let fb = maintenance::update_feedback_review_admin(
        &pool,
        &fb.id,
        &UpdateFeedbackRequest {
            review_status: "in_review".into(),
            verified_label: None,
            resolution_note: Some("Iniciando revisión".into()),
        },
    )
    .await
    .unwrap();
    assert_eq!(fb.review_status, "in_review");

    let fb = maintenance::update_feedback_review_admin(
        &pool,
        &fb.id,
        &UpdateFeedbackRequest {
            review_status: "insufficient_evidence".into(),
            verified_label: Some("UNCERTAIN".into()),
            resolution_note: Some("Audio expirado antes de revisión".into()),
        },
    )
    .await
    .unwrap();
    assert_eq!(fb.review_status, "insufficient_evidence");

    // Importar referencia congelada sintética y comprobar estado insufficient_data -> no_alert -> drift_detected
    let mut input_num = BTreeMap::new();
    input_num.insert(
        "duration_seconds".into(),
        NumericReferenceFeature {
            unit: "s".into(),
            samples: vec![6.0, 6.0, 6.0, 6.0],
            scale: 1.0,
            threshold_normalized_w1: 2.0,
            comparable: true,
            note: None,
        },
    );
    let mut input_cat = BTreeMap::new();
    let mut sr_props = BTreeMap::new();
    sr_props.insert("16000".into(), 1.0);
    input_cat.insert(
        "original_sample_rate".into(),
        CategoricalReferenceFeature {
            proportions: sr_props,
            threshold_max_abs_diff: 0.25,
            comparable: true,
            note: None,
        },
    );
    let mut output_num = BTreeMap::new();
    output_num.insert(
        "score_mean".into(),
        NumericReferenceFeature {
            unit: "sigmoid".into(),
            samples: vec![0.90, 0.91, 0.92, 0.93],
            scale: 0.1,
            threshold_normalized_w1: 1.5,
            comparable: true,
            note: None,
        },
    );

    let ref_payload = DriftReferencePayload {
        id: "ref_unit_test_v1".into(),
        version: "1.0.0-unit".into(),
        name: "Referencia unitaria sintética".into(),
        provenance: "Prueba unitaria Rust".into(),
        observation_unit: "file".into(),
        file_count: 4,
        source_group_count: 1,
        representative_status: "synthetic_demo".into(),
        extraction_version: "obs_v1".into(),
        model_sha256: Some(res.model_sha256.clone()),
        contract_version: Some("1.0.0".into()),
        contract_sha256: Some(res.contract_sha256.clone()),
        min_observations: 3,
        calibration_note: Some("Umbral de prueba unitaria".into()),
        input_numeric: input_num,
        input_categorical: input_cat,
        output_numeric: output_num,
    };
    maintenance::import_drift_reference(&pool, ref_payload)
        .await
        .unwrap();

    // Con solo 1 observación -> insufficient_data
    let e_insuf =
        maintenance::evaluate_drift_and_store(&pool, 30, Some(&res.model_sha256))
            .await
            .unwrap();
    assert_eq!(e_insuf.status, "insufficient_data");

    // Agregar 2 observaciones más comparables -> no_alert
    maintenance::record_completed_job_telemetry(&pool, "job_02", &res, 40.0, 1.0, 2.0, 72.0)
        .await
        .unwrap();
    maintenance::record_completed_job_telemetry(&pool, "job_03", &res, 40.0, 1.0, 2.0, 72.0)
        .await
        .unwrap();
    let e_ok = maintenance::evaluate_drift_and_store(&pool, 30, Some(&res.model_sha256))
        .await
        .unwrap();
    assert_eq!(e_ok.status, "no_alert");

    // Evaluar contra un hash de modelo distinto -> evaluation_error (incompatible)
    let e_incompat =
        maintenance::evaluate_drift_and_store(&pool, 30, Some("ffffffff_other_model"))
            .await
            .unwrap();
    assert_eq!(e_incompat.status, "evaluation_error");

    // Purga de historial antiguo (30 días) conserva drift_references congeladas
    sqlx::query(
        "UPDATE job_telemetry_history SET recorded_at = '2020-01-01T00:00:00Z' WHERE job_id = 'job_01'",
    )
    .execute(&pool)
    .await
    .unwrap();
    let purged = maintenance::purge_expired_maintenance_history(&pool, 30)
        .await
        .unwrap();
    assert_eq!(purged, 1);
    let (refs_left,): (i64,) = sqlx::query_as("SELECT COUNT(*) FROM drift_references")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(refs_left, 1);
}
