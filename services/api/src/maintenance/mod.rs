pub mod auth;
pub mod deployments;
pub mod drift;
pub mod feedback;
pub mod health;
pub mod telemetry;

pub use auth::{get_maintenance_state, set_maintenance_state, verify_admin_token, MaintenanceStateDto};
pub use deployments::{list_recent_deployments, record_model_deployment, ModelDeploymentRow, RecordDeploymentRequest};
pub use drift::{
    evaluate_drift_and_store, get_active_drift_reference, get_drift_status, import_drift_reference,
    wasserstein_1d, CategoricalReferenceFeature, DriftEvaluationDto, DriftReferencePayload,
    DriftReferenceSummary, DriftStatusResponseDto, FeatureDriftMetric, NumericReferenceFeature,
};
pub use feedback::{
    compute_reviewed_feedback_metrics, create_feedback_report, list_all_feedback_admin,
    list_feedback_for_session_job, update_feedback_review_admin, valid_feedback_type,
    valid_review_transition, AdminFeedbackListDto, CreateFeedbackRequest,
    FeedbackMetricsSummaryDto, FeedbackReportDto, UpdateFeedbackRequest,
};
pub use health::{
    measure_sqlite_size_bytes, probe_live_dependencies, record_health_probe_and_incidents,
    ComponentCheckDto, HealthSampleRow, IncidentRow, LiveProbeResult,
};
pub use telemetry::{
    build_admin_overview, classify_error_outcome, mark_telemetry_user_deleted, percentile,
    purge_expired_maintenance_history, record_completed_job_telemetry, record_failed_job_telemetry,
    record_retention_run, summarize_f64, AdminOverviewDto, DurationBucketLatencyDto,
    JobCountersDto, LatencyStagesDto, LatencySummaryDto, MonitoringConfigViewDto, RetentionRunRow,
    StorageMetricsDto,
};
