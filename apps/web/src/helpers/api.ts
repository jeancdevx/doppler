export type JobStatus =
  | 'uploading'
  | 'queued'
  | 'analyzing'
  | 'completed'
  | 'failed'

export interface LimitsInfo {
  allowed_extensions: string[]
  max_file_bytes: number
  max_duration_seconds: number
  min_window_seconds: number
  window_seconds: number
  hop_seconds: number
  retention_hours: number
  max_queue_depth: number
  max_concurrent_inference: number
}

export interface InferenceHealth {
  status: string
  ready: boolean
  model_loaded: boolean
  model_sha256: string | null
  contract_version: string
  contract_sha256: string | null
  threshold: number | null
  score_type: string | null
  input_shape: number[] | null
  torch_version: string
  torch_num_threads: number
  startup_load_ms: number | null
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  api: string
  database: string
  r2_configured: boolean
  r2_reachable: boolean
  queue_active: number
  max_queue_depth: number
  max_concurrent_inference: number
  limits: LimitsInfo
  inference: InferenceHealth | null
}

export interface SessionResponse {
  session_id: string
  limits: LimitsInfo
}

export interface CreateUploadResponse {
  job_id: string
  run_id: string
  status: JobStatus
  upload: {
    method: 'PUT'
    url: string
    headers: Record<string, string>
    expires_in_seconds: number
  }
  expires_at: string
  retention_hours: number
}

export interface WindowPrediction {
  index: number
  start_seconds: number
  end_seconds: number
  score: number
  label: 'EMERGENCY' | 'NON_EMERGENCY'
  margin_vs_threshold: number
}

export interface MergedInterval {
  start_seconds: number
  end_seconds: number
  duration_seconds: number
  window_count: number
  max_score: number
}

export interface AudioInfo {
  original_sample_rate: number
  original_channels: number
  prepared_sample_rate: number
  prepared_channels: number
  duration_seconds: number
  prepared_samples: number
  peak_before_normalization: number
  peak_after_normalization: number
  rms_after_normalization: number
  downmix_cancellation_candidate: boolean
  discarded_tail_samples: number
  discarded_tail_seconds: number
  window_seconds: number
  hop_seconds: number
}

export interface JobTimings {
  client_upload_ms: number | null
  queue_wait_ms: number | null
  r2_fetch_ms: number | null
  decode_and_prepare_ms: number | null
  inference_ms: number | null
  persist_ms: number | null
  total_processing_ms: number | null
}

export interface JobSummary {
  job_id: string
  run_id: string
  filename: string
  status: JobStatus
  declared_size_bytes: number
  actual_size_bytes: number | null
  duration_seconds: number | null
  windows_total: number
  windows_positive: number
  short_clip: boolean
  error_code: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
  expires_at: string
}

export interface JobDetail {
  job_id: string
  run_id: string
  filename: string
  status: JobStatus
  queue_position: number | null
  declared_size_bytes: number
  actual_size_bytes: number | null
  error_code: string | null
  error_message: string | null
  audio_sha256: string | null
  model_sha256: string | null
  contract_version: string | null
  contract_sha256: string | null
  threshold: number | null
  score_type: string | null
  audio: AudioInfo | null
  windows_total: number
  windows_positive: number
  positive_coverage_seconds: number
  positive_coverage_note: string
  merged_positive_intervals: MergedInterval[]
  windows: WindowPrediction[]
  short_clip: boolean
  short_clip_message: string | null
  timings: JobTimings
  created_at: string
  confirmed_at: string | null
  started_at: string | null
  completed_at: string | null
  expires_at: string
}

export interface AudioUrlResponse {
  job_id: string
  url: string
  expires_in_seconds: number
  content_type: string
}

export class ApiClientError extends Error {
  code: string

  status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiClientError'
    this.code = code
    this.status = status
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers ?? {})
    }
  })

  if (!response.ok) {
    let code = 'request_error'
    let message = `La solicitud falló con código HTTP ${response.status}.`

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
      // Mantiene el mensaje genérico cuando la respuesta no es JSON.
    }

    throw new ApiClientError(code, message, response.status)
  }

  return (await response.json()) as T
}

export function fetchHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/api/health')
}

export function ensureSession(): Promise<SessionResponse> {
  return requestJson<SessionResponse>('/api/session', { method: 'POST' })
}

export function listJobs(): Promise<JobSummary[]> {
  return requestJson<JobSummary[]>('/api/jobs')
}

export function fetchJob(jobId: string): Promise<JobDetail> {
  return requestJson<JobDetail>(`/api/jobs/${encodeURIComponent(jobId)}`)
}

export function createUploadSession(payload: {
  filename: string
  size_bytes: number
  content_type: string
}): Promise<CreateUploadResponse> {
  return requestJson<CreateUploadResponse>('/api/uploads', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function confirmUpload(
  jobId: string,
  clientUploadMs: number
): Promise<JobDetail> {
  return requestJson<JobDetail>(
    `/api/jobs/${encodeURIComponent(jobId)}/confirm`,
    {
      method: 'POST',
      body: JSON.stringify({ client_upload_ms: clientUploadMs })
    }
  )
}

export function fetchAudioUrl(jobId: string): Promise<AudioUrlResponse> {
  return requestJson<AudioUrlResponse>(
    `/api/jobs/${encodeURIComponent(jobId)}/audio-url`
  )
}

export async function deleteJob(jobId: string): Promise<void> {
  const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {
    method: 'DELETE',
    credentials: 'same-origin'
  })

  if (!response.ok && response.status !== 204) {
    throw new ApiClientError(
      'delete_error',
      'No se pudo eliminar el trabajo ni su archivo asociado en R2.',
      response.status
    )
  }
}

export function getExportUrl(jobId: string, format: 'json' | 'csv'): string {
  return `/api/jobs/${encodeURIComponent(jobId)}/export?format=${format}`
}

export interface UploadProgressInfo {
  loaded: number
  total: number
  percent: number
  bytesPerSecond: number
}

export function uploadFileToR2(
  file: File,
  target: CreateUploadResponse['upload'],
  onProgress: (info: UploadProgressInfo) => void,
  signal?: AbortSignal
): Promise<{ elapsedMs: number }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const startedAt = performance.now()

    const handleAbort = () => {
      xhr.abort()
    }

    if (signal) {
      if (signal.aborted) {
        reject(
          new ApiClientError('aborted', 'Carga cancelada por el usuario.', 0)
        )

        return
      }

      signal.addEventListener('abort', handleAbort, { once: true })
    }

    xhr.open(target.method, target.url, true)

    for (const [key, value] of Object.entries(target.headers)) {
      xhr.setRequestHeader(key, value)
    }

    xhr.upload.addEventListener('progress', event => {
      if (!event.lengthComputable) {
        return
      }

      const elapsedSeconds = Math.max(
        (performance.now() - startedAt) / 1000,
        0.05
      )
      const percent = Math.min(
        100,
        Math.round((event.loaded / event.total) * 100)
      )

      onProgress({
        loaded: event.loaded,
        total: event.total,
        percent,
        bytesPerSecond: event.loaded / elapsedSeconds
      })
    })

    xhr.addEventListener('load', () => {
      signal?.removeEventListener('abort', handleAbort)

      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress({
          loaded: file.size,
          total: file.size,
          percent: 100,
          bytesPerSecond:
            file.size / Math.max((performance.now() - startedAt) / 1000, 0.05)
        })
        resolve({ elapsedMs: performance.now() - startedAt })
      } else {
        reject(
          new ApiClientError(
            'r2_upload_error',
            `La carga directa a Cloudflare R2 falló (HTTP ${xhr.status}). Comprueba CORS y conectividad.`,
            xhr.status
          )
        )
      }
    })

    xhr.addEventListener('error', () => {
      signal?.removeEventListener('abort', handleAbort)
      reject(
        new ApiClientError(
          'r2_network_error',
          'No se pudo completar la transferencia directa a Cloudflare R2. Verifica la conexión o la regla CORS del bucket.',
          0
        )
      )
    })

    xhr.addEventListener('abort', () => {
      signal?.removeEventListener('abort', handleAbort)
      reject(new ApiClientError('aborted', 'Carga cancelada.', 0))
    })

    xhr.send(file)
  })
}
