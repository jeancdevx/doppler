import {
  ApiClientError,
  type ComponentCheck,
  type FeedbackReport,
  type FeedbackReviewStatus,
  type InferenceHealth
} from './api'

export interface LiveProbeResult {
  checked_at: string
  overall_status: 'healthy' | 'degraded' | 'unavailable' | 'unknown'
  ready_for_traffic: boolean
  maintenance_mode: boolean
  maintenance_reason: string | null
  api: ComponentCheck
  sqlite: ComponentCheck
  inference: ComponentCheck
  r2: ComponentCheck
  queue_depth: number | null
  analyzing_count: number | null
  sqlite_size_bytes: number | null
  r2_managed_bytes: number | null
  r2_managed_objects: number | null
  inference_detail: InferenceHealth | null
}

export interface HealthSample {
  id: number
  checked_at: string
  overall_status: string
  api_status: string
  sqlite_status: string
  sqlite_latency_ms: number | null
  inference_status: string
  inference_latency_ms: number | null
  r2_status: string
  r2_latency_ms: number | null
  queue_depth: number | null
  analyzing_count: number | null
  sqlite_size_bytes: number | null
  r2_managed_bytes: number | null
  r2_managed_objects: number | null
  model_sha256: string | null
  contract_version: string | null
  maintenance_mode: number
  detail: string | null
}

export interface IncidentItem {
  id: string
  component: string
  severity: string
  status: string
  consecutive_failures: number
  opened_at: string
  resolved_at: string | null
  summary: string
  last_error: string | null
}

export interface RetentionRun {
  id: number
  ran_at: string
  scope: string
  jobs_deleted: number
  r2_objects_deleted: number
  r2_errors: number
  history_rows_deleted: number
  duration_ms: number
  status: string
  detail: string | null
}

export interface ModelDeployment {
  id: string
  action: string
  package_version: string
  model_sha256: string | null
  contract_version: string | null
  contract_sha256: string | null
  previous_model_sha256: string | null
  status: string
  reason: string
  details_json: string | null
  created_at: string
}

export interface LatencySummary {
  n: number
  p50_ms: number | null
  p95_ms: number | null
  mean_ms: number | null
}

export interface DurationBucketLatency {
  bucket: string
  n: number
  r2_fetch_p50_ms: number | null
  decode_prepare_p50_ms: number | null
  inference_p50_ms: number | null
  inference_p95_ms: number | null
  total_processing_p50_ms: number | null
  total_processing_p95_ms: number | null
}

export interface JobCounters {
  window_days: number
  total_recorded: number
  completed: number
  user_validation_errors: number
  internal_errors: number
  short_clips: number
  active_jobs_in_24h_table: number
  user_deleted_in_history: number
}

export interface StorageMetrics {
  sqlite_size_bytes: number | null
  sqlite_measurement_method: string
  r2_managed_bytes: number | null
  r2_managed_objects: number | null
  r2_measurement_method: string
}

export interface MonitoringConfigView {
  health_check_interval_seconds: number
  incident_failure_threshold: number
  job_retention_hours: number
  history_retention_days: number
  max_concurrent_inference: number
  max_queue_depth: number
  telemetry_redact_on_user_delete: boolean
}

export interface AdminOverview {
  generated_at: string
  live: LiveProbeResult
  counters: JobCounters
  latencies: {
    queue_wait: LatencySummary
    r2_fetch: LatencySummary
    decode_and_prepare: LatencySummary
    inference: LatencySummary
    persist: LatencySummary
    total_processing: LatencySummary
  }
  latency_by_duration_bucket: DurationBucketLatency[]
  timing_boundary_note: string
  storage: StorageMetrics
  monitoring_config: MonitoringConfigView
  recent_health_samples: HealthSample[]
  incidents: IncidentItem[]
  retention_runs: RetentionRun[]
  model_deployments: ModelDeployment[]
}

export interface DriftReferenceSummary {
  id: string
  version: string
  name: string
  provenance: string
  observation_unit: string
  file_count: number
  source_group_count: number
  representative_status: string
  extraction_version: string
  model_sha256: string | null
  contract_version: string | null
  contract_sha256: string | null
  min_observations: number
  is_active: number
  created_at: string
}

export interface FeatureDriftMetric {
  feature: string
  group: string
  unit: string
  method: string
  n_ref: number
  n_obs: number
  statistic: number | null
  normalized_statistic: number | null
  threshold: number
  ref_mean: number | null
  obs_mean: number | null
  alerted: boolean
  status: string
  note: string | null
}

export interface DriftEvaluation {
  id: string
  reference_id: string | null
  evaluated_at: string
  window_days: number
  sample_count: number
  status: string
  representative_status: string
  input_drift_detected: boolean
  output_drift_detected: boolean
  summary: string
  features: FeatureDriftMetric[]
  warning_note: string
}

export interface DriftStatusResponse {
  active_reference: DriftReferenceSummary | null
  representative_status: string
  latest_evaluation: DriftEvaluation | null
  recent_evaluations: DriftEvaluation[]
}

export interface FeedbackMetricsSummary {
  status: 'unavailable' | 'available_biased_sample'
  total_reports: number
  deduplicated_verified_windows: number
  excluded_uncertain_or_general: number
  confirmed_emergency: number
  confirmed_non_emergency: number
  agreement_rate_on_verified_sample: number | null
  methodology_note: string
}

export interface AdminFeedbackList {
  reports: FeedbackReport[]
  metrics: FeedbackMetricsSummary
}

export interface MaintenanceStateResponse {
  maintenance: {
    enabled: boolean
    reason: string | null
    updated_at: string | null
  }
  analyzing_active: number
  queue_active: number
}

async function requestAdminJson<T>(
  path: string,
  token: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: {
      Accept: 'application/json',
      'X-Admin-Token': token,
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers ?? {})
    }
  })

  if (!response.ok) {
    let code = 'admin_request_error'
    let message = `La solicitud administrativa falló (HTTP ${response.status}).`

    try {
      const data = (await response.json()) as {
        error?: { code?: string; message?: string }
      }

      if (data?.error?.code) {
        code = data.error.code
      }

      if (data?.error?.message) {
        message = data.error.message
      }
    } catch {
      // Mantiene el mensaje genérico si la respuesta no es JSON.
    }

    throw new ApiClientError(code, message, response.status)
  }

  return (await response.json()) as T
}

export function fetchAdminOverview(
  token: string,
  days = 30
): Promise<AdminOverview> {
  return requestAdminJson<AdminOverview>(
    `/api/admin/overview?days=${days}`,
    token
  )
}

export function triggerAdminProbe(token: string): Promise<LiveProbeResult> {
  return requestAdminJson<LiveProbeResult>('/api/admin/health/probe', token, {
    method: 'POST'
  })
}

export function setMaintenanceState(
  token: string,
  enabled: boolean,
  reason: string | null
): Promise<MaintenanceStateResponse> {
  return requestAdminJson<MaintenanceStateResponse>(
    '/api/admin/maintenance',
    token,
    {
      method: 'POST',
      body: JSON.stringify({ enabled, reason })
    }
  )
}

export function fetchAdminDrift(token: string): Promise<DriftStatusResponse> {
  return requestAdminJson<DriftStatusResponse>('/api/admin/drift', token)
}

export function evaluateAdminDrift(
  token: string,
  windowDays = 30
): Promise<DriftEvaluation> {
  return requestAdminJson<DriftEvaluation>('/api/admin/drift/evaluate', token, {
    method: 'POST',
    body: JSON.stringify({ window_days: windowDays })
  })
}

export function fetchAdminFeedback(
  token: string,
  status?: string
): Promise<AdminFeedbackList> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''

  return requestAdminJson<AdminFeedbackList>(`/api/admin/feedback${qs}`, token)
}

export function updateAdminFeedback(
  token: string,
  reportId: string,
  payload: {
    review_status: FeedbackReviewStatus
    verified_label?: string | null
    resolution_note?: string | null
  }
): Promise<FeedbackReport> {
  return requestAdminJson<FeedbackReport>(
    `/api/admin/feedback/${encodeURIComponent(reportId)}`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload)
    }
  )
}
