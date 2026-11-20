-- Migración inicial de Doppler
-- Conserva sesiones anónimas, trabajos, ventanas inferidas y eventos de trazabilidad.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY NOT NULL,
    session_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    declared_size_bytes INTEGER NOT NULL,
    actual_size_bytes INTEGER,
    object_key TEXT NOT NULL UNIQUE,
    r2_etag TEXT,
    status TEXT NOT NULL CHECK (
        status IN (
            'uploading',
            'queued',
            'analyzing',
            'completed',
            'failed'
        )
    ),
    error_code TEXT,
    error_message TEXT,
    audio_sha256 TEXT,
    model_sha256 TEXT,
    contract_version TEXT,
    contract_sha256 TEXT,
    threshold REAL,
    score_type TEXT,
    original_sample_rate INTEGER,
    original_channels INTEGER,
    prepared_sample_rate INTEGER,
    prepared_channels INTEGER,
    duration_seconds REAL,
    prepared_samples INTEGER,
    peak_before_normalization REAL,
    peak_after_normalization REAL,
    rms_after_normalization REAL,
    downmix_cancellation_candidate INTEGER NOT NULL DEFAULT 0,
    discarded_tail_samples INTEGER,
    discarded_tail_seconds REAL,
    window_seconds REAL,
    hop_seconds REAL,
    windows_total INTEGER NOT NULL DEFAULT 0,
    windows_positive INTEGER NOT NULL DEFAULT 0,
    short_clip INTEGER NOT NULL DEFAULT 0,
    short_clip_message TEXT,
    client_upload_ms REAL,
    queue_wait_ms REAL,
    r2_fetch_ms REAL,
    decode_and_prepare_ms REAL,
    inference_ms REAL,
    persist_ms REAL,
    total_processing_ms REAL,
    run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    confirmed_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    expires_at TEXT NOT NULL,
    deleted_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_jobs_session_created ON jobs(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status_confirmed ON jobs(status, confirmed_at ASC);
CREATE INDEX IF NOT EXISTS idx_jobs_expires ON jobs(expires_at);

CREATE TABLE IF NOT EXISTS job_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    window_index INTEGER NOT NULL,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    score REAL NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('EMERGENCY', 'NON_EMERGENCY')),
    margin_vs_threshold REAL NOT NULL,
    UNIQUE(job_id, window_index),
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_job_windows_job ON job_windows(job_id, window_index ASC);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id, id ASC);
