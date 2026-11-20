-- Migración 0002: Monitoreo operativo, detección de drift, retroalimentación y mantenimiento de modelos.
-- Todas las tablas históricas son desacopladas de `jobs` (24 h) y minimizan datos:
-- nunca almacenan WAVs, nombres originales de archivo, URLs firmadas ni secretos.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS health_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at TEXT NOT NULL,
    overall_status TEXT NOT NULL CHECK (
        overall_status IN ('healthy', 'degraded', 'unavailable', 'unknown')
    ),
    api_status TEXT NOT NULL,
    sqlite_status TEXT NOT NULL,
    sqlite_latency_ms REAL,
    inference_status TEXT NOT NULL,
    inference_latency_ms REAL,
    r2_status TEXT NOT NULL,
    r2_latency_ms REAL,
    queue_depth INTEGER,
    analyzing_count INTEGER,
    sqlite_size_bytes INTEGER,
    r2_managed_bytes INTEGER,
    r2_managed_objects INTEGER,
    model_sha256 TEXT,
    contract_version TEXT,
    maintenance_mode INTEGER NOT NULL DEFAULT 0,
    detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_health_samples_checked ON health_samples(checked_at DESC);

CREATE TABLE IF NOT EXISTS operational_incidents (
    id TEXT PRIMARY KEY NOT NULL,
    component TEXT NOT NULL CHECK (
        component IN ('sqlite', 'inference', 'r2', 'queue', 'overall')
    ),
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'critical')),
    status TEXT NOT NULL CHECK (status IN ('open', 'resolved')),
    consecutive_failures INTEGER NOT NULL DEFAULT 1,
    opened_at TEXT NOT NULL,
    resolved_at TEXT,
    summary TEXT NOT NULL,
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_status_opened ON operational_incidents(status, opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_component_status ON operational_incidents(component, status);

-- Observaciones técnicas desacopladas por trabajo (1 fila por job_id, sin duplicados).
-- Sobreviven al borrado automático de 24 h; retención configurable (30 días por defecto).
-- No conserva filename, object_key, cookies ni URLs firmadas.
CREATE TABLE IF NOT EXISTS job_telemetry_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE,
    recorded_at TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (
        outcome IN ('completed', 'user_validation_error', 'internal_error')
    ),
    error_code TEXT,
    model_sha256 TEXT,
    contract_version TEXT,
    contract_sha256 TEXT,
    threshold REAL,
    extraction_version TEXT,
    original_sample_rate INTEGER,
    original_channels INTEGER,
    duration_seconds REAL,
    peak_before_normalization REAL,
    rms_before_normalization REAL,
    rms_after_normalization REAL,
    silence_ratio REAL,
    clipping_ratio REAL,
    downmix_cancellation_candidate INTEGER NOT NULL DEFAULT 0,
    short_clip INTEGER NOT NULL DEFAULT 0,
    discarded_tail_seconds REAL,
    logmel_mean REAL,
    logmel_std REAL,
    spectral_centroid_hz REAL,
    windows_total INTEGER NOT NULL DEFAULT 0,
    windows_positive INTEGER NOT NULL DEFAULT 0,
    positive_window_ratio REAL,
    score_mean REAL,
    score_max REAL,
    score_min REAL,
    score_std REAL,
    r2_fetch_ms REAL,
    queue_wait_ms REAL,
    decode_and_prepare_ms REAL,
    inference_ms REAL,
    persist_ms REAL,
    total_processing_ms REAL,
    user_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_telemetry_recorded ON job_telemetry_history(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_outcome ON job_telemetry_history(outcome, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_model ON job_telemetry_history(model_sha256, recorded_at DESC);

CREATE TABLE IF NOT EXISTS retention_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('jobs_24h', 'maintenance_history')),
    jobs_deleted INTEGER NOT NULL DEFAULT 0,
    r2_objects_deleted INTEGER NOT NULL DEFAULT 0,
    r2_errors INTEGER NOT NULL DEFAULT 0,
    history_rows_deleted INTEGER NOT NULL DEFAULT 0,
    duration_ms REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL CHECK (status IN ('ok', 'partial', 'error')),
    detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_retention_runs_ran ON retention_runs(ran_at DESC);

-- Referencias congeladas de drift (excluidas de la purga de 30 días).
CREATE TABLE IF NOT EXISTS drift_references (
    id TEXT PRIMARY KEY NOT NULL,
    version TEXT NOT NULL,
    name TEXT NOT NULL,
    provenance TEXT NOT NULL,
    observation_unit TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    source_group_count INTEGER NOT NULL,
    representative_status TEXT NOT NULL CHECK (
        representative_status IN (
            'pending_representative_corpus',
            'synthetic_demo',
            'representative_validated'
        )
    ),
    extraction_version TEXT NOT NULL,
    model_sha256 TEXT,
    contract_version TEXT,
    contract_sha256 TEXT,
    min_observations INTEGER NOT NULL DEFAULT 15,
    reference_json TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_drift_refs_active ON drift_references(is_active, created_at DESC);

CREATE TABLE IF NOT EXISTS drift_evaluations (
    id TEXT PRIMARY KEY NOT NULL,
    reference_id TEXT,
    evaluated_at TEXT NOT NULL,
    window_days INTEGER NOT NULL,
    sample_count INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'no_reference',
            'insufficient_data',
            'no_alert',
            'drift_detected',
            'evaluation_error'
        )
    ),
    representative_status TEXT NOT NULL,
    input_drift_detected INTEGER NOT NULL DEFAULT 0,
    output_drift_detected INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL,
    details_json TEXT NOT NULL,
    FOREIGN KEY (reference_id) REFERENCES drift_references(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_drift_evals_at ON drift_evaluations(evaluated_at DESC);

-- Canal de retroalimentación del usuario con máquina de estados auditada.
-- Los reportes NO extienden la retención de 24 h del audio WAV.
CREATE TABLE IF NOT EXISTS feedback_reports (
    id TEXT PRIMARY KEY NOT NULL,
    session_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    window_index INTEGER,
    feedback_type TEXT NOT NULL CHECK (
        feedback_type IN (
            'false_alarm',
            'missed_emergency',
            'technical_issue',
            'uncertain_or_other'
        )
    ),
    comment TEXT,
    displayed_label TEXT,
    displayed_score REAL,
    displayed_threshold REAL,
    window_start_seconds REAL,
    window_end_seconds REAL,
    model_sha256 TEXT,
    contract_version TEXT,
    contract_sha256 TEXT,
    audio_available_at_report INTEGER NOT NULL DEFAULT 1,
    audio_expires_at TEXT,
    review_status TEXT NOT NULL CHECK (
        review_status IN (
            'received',
            'in_review',
            'confirmed',
            'dismissed',
            'insufficient_evidence',
            'resolved'
        )
    ),
    verified_label TEXT CHECK (
        verified_label IS NULL OR verified_label IN ('EMERGENCY', 'NON_EMERGENCY', 'UNCERTAIN')
    ),
    resolution_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reviewed_at TEXT,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_feedback_session_job ON feedback_reports(session_id, job_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback_reports(review_status, created_at DESC);

CREATE TABLE IF NOT EXISTS feedback_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (report_id) REFERENCES feedback_reports(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_feedback_events_report ON feedback_events(report_id, id ASC);

-- Estado de mantenimiento controlado (fila única id=1) y auditoría de actualizaciones de modelo.
CREATE TABLE IF NOT EXISTS maintenance_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO maintenance_state (id, enabled, reason, updated_at)
VALUES (1, 0, NULL, '2026-01-01T00:00:00Z');

CREATE TABLE IF NOT EXISTS model_deployments (
    id TEXT PRIMARY KEY NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('validate', 'activate', 'rollback', 'reject')),
    package_version TEXT NOT NULL,
    model_sha256 TEXT,
    contract_version TEXT,
    contract_sha256 TEXT,
    previous_model_sha256 TEXT,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed', 'rolled_back')),
    reason TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_model_deployments_created ON model_deployments(created_at DESC);
