<script lang="ts">
  import { onDestroy, onMount } from 'svelte'
  import { Tabs } from 'bits-ui'
  import ArrowCounterClockwise from 'phosphor-svelte/lib/ArrowCounterClockwise'
  import CaretLeft from 'phosphor-svelte/lib/CaretLeft'
  import CaretRight from 'phosphor-svelte/lib/CaretRight'
  import CloudArrowUp from 'phosphor-svelte/lib/CloudArrowUp'
  import DownloadSimple from 'phosphor-svelte/lib/DownloadSimple'
  import FileAudio from 'phosphor-svelte/lib/FileAudio'
  import Moon from 'phosphor-svelte/lib/Moon'
  import Pause from 'phosphor-svelte/lib/Pause'
  import Play from 'phosphor-svelte/lib/Play'
  import Sun from 'phosphor-svelte/lib/Sun'
  import Trash from 'phosphor-svelte/lib/Trash'
  import WarningCircle from 'phosphor-svelte/lib/WarningCircle'
  import { Toaster, toast } from 'svelte-sonner'

  import { AudioDropzone } from '@/components/AudioDropzone'
  import { MetricGrid } from '@/components/MetricGrid'
  import {
    PipelineStepper,
    type StudioPhase
  } from '@/components/PipelineStepper'
  import { SpectrogramCanvas } from '@/components/SpectrogramCanvas'
  import { ConfirmDeleteDialog } from '@/components/ui/alert-dialog'
  import { Badge } from '@/components/ui/badge'
  import { Button } from '@/components/ui/button'
  import { Skeleton } from '@/components/ui/skeleton'
  import { WaveformCanvas } from '@/components/WaveformCanvas'
  import { WindowScoreChart } from '@/components/WindowScoreChart'
  import { WindowTable } from '@/components/WindowTable'
  import { DOPPLER_DEFAULTS } from '@/constants/doppler'
  import {
    ApiClientError,
    type HealthResponse,
    type JobDetail,
    type JobSummary,
    type LimitsInfo,
    type UploadProgressInfo,
    confirmUpload,
    createUploadSession,
    deleteJob,
    ensureSession,
    fetchAudioUrl,
    fetchHealth,
    fetchJob,
    getExportUrl,
    listJobs,
    uploadFileToR2
  } from '@/helpers/api'
  import {
    formatBytes,
    formatClock,
    formatSeconds,
    middleTruncate
  } from '@/helpers/format'
  import {
    type ComputedSpectrogram,
    computeRealSpectrogram,
    extractWaveformPeaks,
    prevalidateWavFile
  } from '@/helpers/wav'

  import TraceabilityPanel from './TraceabilityPanel.svelte'

  const DEFAULT_LIMITS: LimitsInfo = {
    allowed_extensions: ['.wav'],
    max_file_bytes: DOPPLER_DEFAULTS.maxFileBytes,
    max_duration_seconds: DOPPLER_DEFAULTS.maxDurationSeconds,
    min_window_seconds: DOPPLER_DEFAULTS.minWindowSeconds,
    window_seconds: DOPPLER_DEFAULTS.windowSeconds,
    hop_seconds: DOPPLER_DEFAULTS.hopSeconds,
    retention_hours: DOPPLER_DEFAULTS.retentionHours,
    max_queue_depth: 16,
    max_concurrent_inference: 1
  }

  let studioTheme = $state<'dark' | 'light'>('dark')
  let health = $state.raw<HealthResponse | null>(null)
  let limits = $state.raw<LimitsInfo>(DEFAULT_LIMITS)
  let jobs = $state.raw<JobSummary[]>([])
  let activeJob = $state.raw<JobDetail | null>(null)
  let selectedWindowIndex = $state<number | null>(null)
  let activeView = $state<'waveform' | 'spectrogram'>('waveform')

  let phase = $state<StudioPhase>('idle')
  let activeFilename = $state<string | null>(null)
  let uploadProgress = $state<UploadProgressInfo | null>(null)
  let errorBanner = $state<{ code: string; message: string } | null>(null)
  let lastFailedFile = $state.raw<File | null>(null)

  let loadingSession = $state(true)
  let showUploadPanel = $state(false)
  let deleteDialogOpen = $state(false)
  let deletingJob = $state(false)

  // Audio local / R2 temporal para forma de onda, espectrograma y reproducción
  let audioEl = $state<HTMLAudioElement | undefined>(undefined)
  let audioSrc = $state<string | null>(null)
  let isPlaying = $state(false)
  let currentTime = $state(0)
  let audioDuration = $state(0)
  let waveformPeaks = $state.raw<Float32Array | null>(null)
  let spectrogramData = $state.raw<ComputedSpectrogram | null>(null)
  let loadingAudioVisuals = $state(false)

  let uploadAbortController: AbortController | null = null
  let pollTimer: number | null = null
  let rafId: number | null = null
  let localObjectUrl: string | null = null

  let busy = $derived(
    phase === 'validating' ||
      phase === 'uploading' ||
      phase === 'queued' ||
      phase === 'analyzing'
  )

  let selectedWindow = $derived(
    activeJob && selectedWindowIndex !== null
      ? activeJob.windows[selectedWindowIndex] ?? null
      : null
  )

  let displayDuration = $derived(
    audioDuration > 0 ? audioDuration : activeJob?.audio?.duration_seconds ?? 0
  )

  function stopPolling() {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  function stopPlayback() {
    if (audioEl) {
      audioEl.pause()
    }

    isPlaying = false

    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
  }

  function revokeLocalObjectUrl() {
    if (localObjectUrl) {
      URL.revokeObjectURL(localObjectUrl)
      localObjectUrl = null
    }
  }

  function toggleTheme() {
    studioTheme = studioTheme === 'dark' ? 'light' : 'dark'

    try {
      window.localStorage.setItem('doppler-studio-theme', studioTheme)
    } catch {
      // Ignora restricciones de almacenamiento del navegador.
    }
  }

  async function decodeAndComputeVisuals(arrayBuffer: ArrayBuffer) {
    loadingAudioVisuals = true

    try {
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext
      const ctx = new AudioCtx()

      try {
        const decoded = await ctx.decodeAudioData(arrayBuffer.slice(0))

        audioDuration = decoded.duration
        waveformPeaks = extractWaveformPeaks(decoded, 320)
        spectrogramData = computeRealSpectrogram(decoded, 240, 64)
      } finally {
        await ctx.close()
      }
    } catch {
      waveformPeaks = null
      spectrogramData = null
    } finally {
      loadingAudioVisuals = false
    }
  }

  async function loadAuthorizedAudioForJob(jobId: string) {
    try {
      const res = await fetchAudioUrl(jobId)

      revokeLocalObjectUrl()
      audioSrc = res.url

      const audioResp = await fetch(res.url)

      if (audioResp.ok) {
        const buf = await audioResp.arrayBuffer()

        await decodeAndComputeVisuals(buf)
      }
    } catch {
      // El usuario aún puede consultar resultados numéricos si la URL temporal expira.
    }
  }

  async function refreshJobsList() {
    try {
      jobs = await listJobs()
    } catch {
      // Mantiene la lista actual si falla un refresco puntual.
    }
  }

  function pickDefaultWindow(job: JobDetail): number | null {
    if (!job.windows.length) {
      return null
    }

    const firstEmergency = job.windows.findIndex(w => w.label === 'EMERGENCY')

    return firstEmergency >= 0 ? firstEmergency : 0
  }

  function schedulePoll(jobId: string) {
    stopPolling()
    pollTimer = window.setTimeout(async () => {
      try {
        const detail = await fetchJob(jobId)

        activeJob = detail

        if (detail.status === 'queued') {
          phase = 'queued'
          schedulePoll(jobId)
        } else if (detail.status === 'analyzing') {
          phase = 'analyzing'
          schedulePoll(jobId)
        } else if (detail.status === 'completed') {
          phase = 'completed'
          showUploadPanel = false
          selectedWindowIndex = pickDefaultWindow(detail)
          await refreshJobsList()

          if (detail.short_clip) {
            toast.info(
              'Audio menor de 3,0 s. No se generaron ventanas completas.'
            )
          } else {
            toast.success(
              `Análisis completado: ${detail.windows_positive} de ${detail.windows_total} ventanas con detección.`
            )
          }

          if (!audioSrc) {
            await loadAuthorizedAudioForJob(detail.job_id)
          }
        } else if (detail.status === 'failed') {
          phase = 'error'
          errorBanner = {
            code: detail.error_code ?? 'inference_error',
            message:
              detail.error_message ??
              'El análisis no pudo completarse. Intenta con otro archivo WAV.'
          }
          await refreshJobsList()
          toast.error(errorBanner.message)
        }
      } catch (err) {
        phase = 'error'
        const message =
          err instanceof Error
            ? err.message
            : 'No se pudo consultar el estado del trabajo.'

        errorBanner = { code: 'poll_error', message }
      }
    }, 900)
  }

  async function selectExistingJob(jobId: string) {
    stopPolling()
    stopPlayback()
    errorBanner = null
    showUploadPanel = false
    currentTime = 0
    audioDuration = 0
    waveformPeaks = null
    spectrogramData = null
    audioSrc = null

    try {
      const detail = await fetchJob(jobId)

      activeJob = detail
      activeFilename = detail.filename
      selectedWindowIndex = pickDefaultWindow(detail)

      if (detail.status === 'completed') {
        phase = 'completed'
        await loadAuthorizedAudioForJob(detail.job_id)
      } else if (detail.status === 'failed') {
        phase = 'error'
        errorBanner = {
          code: detail.error_code ?? 'failed',
          message: detail.error_message ?? 'El trabajo finalizó con error.'
        }
      } else if (detail.status === 'queued' || detail.status === 'analyzing') {
        phase = detail.status
        schedulePoll(detail.job_id)
      } else {
        phase = 'idle'
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : 'No se pudo cargar el trabajo.'
      )
    }
  }

  async function handleSelectFile(file: File) {
    stopPolling()
    stopPlayback()
    revokeLocalObjectUrl()
    errorBanner = null
    lastFailedFile = file
    activeFilename = file.name
    activeJob = null
    selectedWindowIndex = null
    waveformPeaks = null
    spectrogramData = null
    audioSrc = null
    currentTime = 0
    audioDuration = 0
    showUploadPanel = true
    phase = 'validating'

    const localCheck = await prevalidateWavFile(
      file,
      limits.max_file_bytes,
      limits.max_duration_seconds
    )

    if (!localCheck.valid) {
      phase = 'error'
      errorBanner = {
        code: localCheck.errorCode ?? 'validation_error',
        message: localCheck.errorMessage ?? 'Archivo WAV inválido.'
      }
      toast.error(errorBanner.message)

      return
    }

    const localBuf = await file.arrayBuffer()

    await decodeAndComputeVisuals(localBuf)
    localObjectUrl = URL.createObjectURL(file)
    audioSrc = localObjectUrl

    try {
      const contentType =
        file.type === 'audio/x-wav' || file.type === 'audio/wave'
          ? file.type
          : 'audio/wav'

      const uploadSession = await createUploadSession({
        filename: file.name,
        size_bytes: file.size,
        content_type: contentType
      })

      phase = 'uploading'
      uploadProgress = {
        loaded: 0,
        total: file.size,
        percent: 0,
        bytesPerSecond: 0
      }

      uploadAbortController = new AbortController()

      const { elapsedMs } = await uploadFileToR2(
        file,
        uploadSession.upload,
        info => {
          uploadProgress = info
        },
        uploadAbortController.signal
      )

      uploadAbortController = null

      const confirmed = await confirmUpload(uploadSession.job_id, elapsedMs)

      activeJob = confirmed
      phase =
        confirmed.status === 'analyzing'
          ? 'analyzing'
          : confirmed.status === 'completed'
            ? 'completed'
            : 'queued'

      await refreshJobsList()

      if (confirmed.status === 'completed') {
        showUploadPanel = false
        selectedWindowIndex = pickDefaultWindow(confirmed)
      } else {
        schedulePoll(confirmed.job_id)
      }
    } catch (err) {
      uploadAbortController = null
      phase = 'error'
      const code = err instanceof ApiClientError ? err.code : 'upload_error'
      const message =
        err instanceof Error
          ? err.message
          : 'Ocurrió un error inesperado al cargar el audio.'

      errorBanner = { code, message }

      if (code !== 'aborted') {
        toast.error(message)
      } else {
        toast.info('Carga cancelada.')
      }
    }
  }

  function handleCancelUpload() {
    uploadAbortController?.abort()
    uploadAbortController = null
  }

  function handleRetryLastFile() {
    if (lastFailedFile) {
      void handleSelectFile(lastFailedFile)
    }
  }

  /**
   * Sincroniza la ventana activa respecto a un instante temporal teniendo en cuenta
   * el solapamiento del 50 % (3,0 s / salto 1,5 s):
   * - Si la ventana actualmente seleccionada sigue conteniendo `timeSec`, se respeta
   *   para evitar saltos hacia atrás a la ventana anterior solapada.
   * - En caso contrario, selecciona la ventana que contiene `timeSec` cuyo centro
   *   está más cerca de `timeSec`.
   */
  function syncWindowToTime(timeSec: number) {
    if (!activeJob || !activeJob.windows.length) {
      return
    }

    if (selectedWindowIndex !== null) {
      const currentWin = activeJob.windows[selectedWindowIndex]

      if (
        currentWin &&
        timeSec >= currentWin.start_seconds &&
        timeSec < currentWin.end_seconds
      ) {
        return
      }
    }

    let bestIndex = -1
    let bestDistance = Number.POSITIVE_INFINITY

    for (const win of activeJob.windows) {
      if (timeSec >= win.start_seconds && timeSec < win.end_seconds) {
        const center = (win.start_seconds + win.end_seconds) / 2
        const dist = Math.abs(timeSec - center)

        if (dist <= bestDistance) {
          bestDistance = dist
          bestIndex = win.index
        }
      }
    }

    if (bestIndex >= 0 && bestIndex !== selectedWindowIndex) {
      selectedWindowIndex = bestIndex
    }
  }

  function startPlayheadLoop() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
    }

    const step = () => {
      if (!audioEl || audioEl.paused) {
        isPlaying = false
        rafId = null

        return
      }

      currentTime = audioEl.currentTime
      syncWindowToTime(currentTime)
      rafId = requestAnimationFrame(step)
    }

    rafId = requestAnimationFrame(step)
  }

  async function togglePlay() {
    if (!audioEl || !audioSrc) {
      if (activeJob && activeJob.status === 'completed') {
        await loadAuthorizedAudioForJob(activeJob.job_id)
      }

      if (!audioEl || !audioSrc) {
        toast.info('Audio todavía no disponible para reproducción.')

        return
      }
    }

    if (isPlaying) {
      stopPlayback()

      return
    }

    try {
      if (displayDuration > 0 && currentTime >= displayDuration - 0.05) {
        audioEl.currentTime = 0
        currentTime = 0
      }

      await audioEl.play()
      isPlaying = true
      startPlayheadLoop()
    } catch {
      toast.error(
        'El navegador bloqueó la reproducción o expiró el acceso temporal.'
      )
    }
  }

  function seekTo(seconds: number, syncWindow = true) {
    const clamped = Math.max(0, Math.min(displayDuration || seconds, seconds))

    currentTime = clamped

    if (audioEl && audioSrc) {
      audioEl.currentTime = clamped
    }

    if (syncWindow) {
      syncWindowToTime(clamped)
    }
  }

  function handleSelectWindow(index: number, seekAudio: boolean) {
    selectedWindowIndex = index

    const win = activeJob?.windows[index]

    if (win && seekAudio) {
      // Mantiene fija la ventana explícitamente elegida por el usuario aunque solape con la anterior
      seekTo(win.start_seconds, false)
    }
  }

  function stepWindow(delta: number) {
    if (!activeJob || !activeJob.windows.length) {
      return
    }

    const base = selectedWindowIndex ?? 0
    const next = Math.max(
      0,
      Math.min(activeJob.windows.length - 1, base + delta)
    )

    handleSelectWindow(next, true)
  }

  async function handleConfirmDelete() {
    if (!activeJob) {
      return
    }

    deletingJob = true
    const targetId = activeJob.job_id

    try {
      stopPolling()
      stopPlayback()
      await deleteJob(targetId)
      deleteDialogOpen = false
      activeJob = null
      activeFilename = null
      selectedWindowIndex = null
      waveformPeaks = null
      spectrogramData = null
      audioSrc = null
      phase = 'idle'
      showUploadPanel = false
      await refreshJobsList()
      toast.success('Archivo y resultados eliminados de R2 y SQLite.')
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : 'No se pudo eliminar el trabajo.'
      )
    } finally {
      deletingJob = false
    }
  }

  function handleExport(format: 'json' | 'csv') {
    if (!activeJob || activeJob.status !== 'completed') {
      return
    }

    window.location.href = getExportUrl(activeJob.job_id, format)
    toast.success(`Exportación ${format.toUpperCase()} iniciada.`)
  }

  function openNewUpload() {
    stopPlayback()
    errorBanner = null
    showUploadPanel = true

    if (phase === 'error') {
      phase = 'idle'
    }

    window.setTimeout(() => {
      document.getElementById('doppler-wav-input')?.click()
    }, 40)
  }

  onMount(() => {
    try {
      const saved = window.localStorage.getItem('doppler-studio-theme')

      if (saved === 'light' || saved === 'dark') {
        studioTheme = saved
      }
    } catch {
      // Usa oscuro por defecto.
    }

    const triggerUploadHandler = () => {
      document.getElementById('studio')?.scrollIntoView({ behavior: 'smooth' })
      openNewUpload()
    }

    window.addEventListener('doppler:trigger-upload', triggerUploadHandler)

    void (async () => {
      try {
        const [h, s] = await Promise.all([
          fetchHealth().catch(() => null),
          ensureSession().catch(() => null)
        ])

        health = h

        if (s?.limits) {
          limits = s.limits
        } else if (h?.limits) {
          limits = h.limits
        }

        const existing = await listJobs().catch(() => [])

        jobs = existing

        if (existing.length > 0) {
          await selectExistingJob(existing[0].job_id)
        }
      } finally {
        loadingSession = false
      }
    })()

    return () => {
      window.removeEventListener('doppler:trigger-upload', triggerUploadHandler)
    }
  })

  onDestroy(() => {
    stopPolling()
    stopPlayback()
    revokeLocalObjectUrl()
  })
</script>

<Toaster position="bottom-right" theme={studioTheme} richColors />

<audio
  bind:this={audioEl}
  src={audioSrc ?? undefined}
  preload="metadata"
  crossorigin="anonymous"
  onended={() => {
    isPlaying = false
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
  }}
  ontimeupdate={() => {
    if (audioEl && !isPlaying) {
      currentTime = audioEl.currentTime
    }
  }}
></audio>

<div
  data-studio-theme={studioTheme}
  id="doppler-workbench"
  class={[
    'relative overflow-hidden rounded-2xl border bg-[var(--studio-bg)] text-[var(--studio-text)] shadow-[0_28px_70px_-28px_rgba(9,15,29,0.55)] transition-colors',
    busy ? 'border-[var(--studio-accent)]' : 'border-[var(--studio-border)]'
  ]}
>
  <!-- Reflejo superior del chasis del instrumento -->
  <div
    class="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-[var(--studio-accent)]/55 to-transparent"
    aria-hidden="true"
  ></div>

  <!-- Barra superior tipo rack de instrumento DAW -->
  <div
    class="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--studio-border)] bg-[var(--studio-panel)] px-4 py-3.5 sm:px-6"
  >
    <div class="flex min-w-0 items-center gap-3">
      <img
        src={studioTheme === 'dark'
          ? '/logos/doppler-symbol-reverse.svg'
          : '/logos/doppler-symbol-primary.svg'}
        alt=""
        class="size-7 shrink-0"
      />
      <div class="flex min-w-0 flex-wrap items-baseline gap-2">
        <span class="title-3 font-semibold text-[var(--studio-text)]">
          Estudio acústico
        </span>
        <span
          class="hidden rounded-md border border-[var(--studio-border)] bg-[var(--studio-bg)] px-2 py-0.5 font-mono text-[10px] tracking-[0.06em] text-[var(--studio-muted)] sm:inline-block"
        >
          RESNET18 · LOG-MEL 64×94 · CPU
        </span>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      {#if health}
        <Badge tone={health.status === 'ok' ? 'ok' : 'error'} dot>
          {health.status === 'ok'
            ? 'Modelo + R2 listos'
            : health.r2_reachable
              ? 'Inferencia iniciando'
              : 'Revisar R2'}
        </Badge>
      {:else}
        <Badge tone="neutral">Verificando estado…</Badge>
      {/if}

      <!-- Conmutador táctil claro/oscuro del estudio -->
      <button
        type="button"
        class="inline-flex min-h-[34px] cursor-pointer items-center gap-1.5 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] px-2.5 py-1 text-xs font-medium text-[var(--studio-text)] transition-colors hover:border-[var(--studio-accent)]"
        aria-label={studioTheme === 'dark'
          ? 'Cambiar estudio a tema claro'
          : 'Cambiar estudio a tema oscuro'}
        title={studioTheme === 'dark' ? 'Tema claro' : 'Tema oscuro'}
        onclick={toggleTheme}
      >
        {#if studioTheme === 'dark'}
          <Sun class="size-4 text-[#f0c779]" aria-hidden="true" />
          <span class="hidden sm:inline">Claro</span>
        {:else}
          <Moon class="size-4 text-[#3156d3]" aria-hidden="true" />
          <span class="hidden sm:inline">Oscuro</span>
        {/if}
      </button>

      {#if activeJob && activeJob.status === 'completed'}
        <div
          class="inline-flex items-center overflow-hidden rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)]"
        >
          <button
            type="button"
            class="inline-flex min-h-[34px] cursor-pointer items-center gap-1.5 border-r border-[var(--studio-border)] px-3 py-1 font-mono text-xs text-[var(--studio-text)] transition-colors hover:bg-[var(--studio-raised)]"
            onclick={() => handleExport('json')}
          >
            <DownloadSimple class="size-3.5" aria-hidden="true" />
            <span>JSON</span>
          </button>
          <button
            type="button"
            class="inline-flex min-h-[34px] cursor-pointer items-center gap-1.5 px-3 py-1 font-mono text-xs text-[var(--studio-text)] transition-colors hover:bg-[var(--studio-raised)]"
            onclick={() => handleExport('csv')}
          >
            <DownloadSimple class="size-3.5" aria-hidden="true" />
            <span>CSV</span>
          </button>
        </div>

        <Button
          variant="danger"
          size="icon"
          aria-label="Eliminar archivo y resultados"
          title="Eliminar archivo de R2 y resultados"
          onclick={() => {
            deleteDialogOpen = true
          }}
        >
          <Trash class="size-4" aria-hidden="true" />
        </Button>
      {/if}
    </div>
  </div>

  <!-- Cuerpo principal: riel de sesión (272px) + consola protagonista (>=74%) -->
  <div class="grid grid-cols-1 lg:grid-cols-[272px_minmax(0,1fr)]">
    <aside
      class="flex flex-col gap-4 border-b border-[var(--studio-border)] bg-[var(--studio-panel)]/55 p-4 lg:border-r lg:border-b-0"
      aria-label="Archivos analizados en esta sesión"
    >
      <div class="flex items-center justify-between gap-2">
        <span class="caption-4 font-mono text-[var(--studio-muted)]">
          SESIÓN ACTUAL
        </span>
        <span
          class="rounded border border-[var(--studio-border)] bg-[var(--studio-bg)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--studio-text)] tabular-nums"
        >
          {String(jobs.length).padStart(2, '0')}
        </span>
      </div>

      <Button
        variant="subtle"
        size="sm"
        class="w-full justify-center"
        disabled={busy}
        onclick={openNewUpload}
      >
        <CloudArrowUp class="size-4" aria-hidden="true" />
        <span>Cargar nuevo WAV</span>
      </Button>

      {#if loadingSession}
        <div class="flex flex-col gap-2">
          <Skeleton class="h-14 w-full" />
          <Skeleton class="h-14 w-full" />
        </div>
      {:else if jobs.length === 0}
        <p
          class="body-6 rounded-xl border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3.5 text-xs text-[var(--studio-muted)]"
        >
          Todavía no hay archivos en esta sesión. Los análisis completados permanecen disponibles 24 h salvo que los elimines antes.
        </p>
      {:else}
        <ul
          class="flex max-h-[220px] flex-col gap-2 overflow-y-auto lg:max-h-[480px]"
        >
          {#each jobs as item (item.job_id)}
            {@const isCurrent = activeJob?.job_id === item.job_id}
            {@const hasPositive = item.status === 'completed' && item.windows_positive > 0}
            <li>
              <button
                type="button"
                class={[
                  'relative flex w-full cursor-pointer items-start gap-2.5 overflow-hidden rounded-xl border p-3 pl-3.5 text-left transition-colors',
                  isCurrent
                    ? 'border-[var(--studio-accent)] bg-[var(--studio-raised)]'
                    : 'border-[var(--studio-border)] bg-[var(--studio-bg)] hover:border-[var(--studio-accent)]/60'
                ]}
                onclick={() => void selectExistingJob(item.job_id)}
              >
                <span
                  class={[
                    'absolute inset-y-2 left-0 w-1 rounded-r-full',
                    item.status === 'failed'
                      ? 'bg-[#e37d85]'
                      : hasPositive
                        ? 'bg-[#f0c779]'
                        : item.status === 'completed'
                          ? 'bg-[#86d6b8]'
                          : 'bg-[var(--studio-accent)]'
                  ]}
                  aria-hidden="true"
                ></span>
                <FileAudio
                  class="mt-0.5 size-4 shrink-0 text-[var(--studio-accent)]"
                  aria-hidden="true"
                />
                <div class="min-w-0 flex-1">
                  <span
                    class="block truncate text-xs font-medium text-[var(--studio-text)]"
                    title={item.filename}
                  >
                    {middleTruncate(item.filename, 24)}
                  </span>
                  <span
                    class="mt-0.5 block font-mono text-[11px] text-[var(--studio-muted)] tabular-nums"
                  >
                    {#if item.status === 'completed'}
                      {item.short_clip
                        ? 'Menor a 3,0 s'
                        : `${item.windows_positive}/${item.windows_total} positivas · ${formatSeconds(item.duration_seconds)}`}
                    {:else if item.status === 'failed'}
                      Error · {item.error_code ?? 'fallo'}
                    {:else}
                      {item.status === 'queued'
                        ? 'En cola…'
                        : item.status === 'analyzing'
                          ? 'Analizando…'
                          : 'Subiendo…'}
                    {/if}
                  </span>
                </div>
              </button>
            </li>
          {/each}
        </ul>
      {/if}

      <div
        class="mt-auto hidden rounded-xl border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3.5 text-xs text-[var(--studio-muted)] lg:block"
      >
        <p class="font-mono text-[10px] tracking-[0.06em] text-[var(--studio-accent)]">
          CONTRATO CONGELADO
        </p>
        <p class="mt-1 font-medium text-[var(--studio-text)]">
          Escucha. Observa. Contrasta.
        </p>
        <p class="mt-1 leading-relaxed">
          Umbral <span class="font-mono text-[var(--studio-text)]">0,6548</span>.
          Almacenamiento en R2 privado con purga automática a las {limits.retention_hours} h.
        </p>
      </div>
    </aside>

    <!-- Consola protagonista -->
    <div class="flex min-w-0 flex-col gap-5 p-4 sm:p-6">
      <PipelineStepper
        {phase}
        uploadPercent={uploadProgress?.percent ?? 0}
        queuePosition={activeJob?.queue_position ?? null}
        timings={activeJob?.timings ?? null}
      />

      {#if errorBanner}
        <div
          role="alert"
          class="flex flex-wrap items-start justify-between gap-4 rounded-xl border border-[var(--badge-error-border)] bg-[var(--badge-error-bg)] p-4 text-sm text-[var(--badge-error-text)]"
        >
          <div class="flex min-w-0 items-start gap-3">
            <WarningCircle class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
            <div class="min-w-0">
              <p class="font-medium">No se pudo completar el análisis</p>
              <p class="mt-1 text-xs opacity-90">{errorBanner.message}</p>
              <p class="mt-1 font-mono text-[11px] opacity-75">
                Código: {errorBanner.code}
              </p>
            </div>
          </div>
          <div class="flex shrink-0 flex-wrap gap-2">
            {#if lastFailedFile && errorBanner.code !== 'invalid_extension' && errorBanner.code !== 'size_exceeded' && errorBanner.code !== 'duration_exceeded'}
              <Button variant="outline" size="sm" onclick={handleRetryLastFile}>
                <ArrowCounterClockwise class="size-4" aria-hidden="true" />
                <span>Reintentar</span>
              </Button>
            {/if}
            <Button variant="subtle" size="sm" onclick={openNewUpload}>
              Elegir otro WAV
            </Button>
          </div>
        </div>
      {/if}

      {#if showUploadPanel || (!activeJob && phase !== 'completed')}
        <AudioDropzone
          {limits}
          {busy}
          uploading={phase === 'uploading'}
          {activeFilename}
          {uploadProgress}
          onSelectFile={file => void handleSelectFile(file)}
          onCancelUpload={handleCancelUpload}
        />
      {/if}

      {#if activeJob && (phase === 'queued' || phase === 'analyzing')}
        <div
          class="flex flex-col gap-4 rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-5"
          aria-live="polite"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 class="heading-4 text-[var(--studio-text)]">
                {phase === 'queued'
                  ? 'En cola de procesamiento'
                  : 'Ejecutando ResNet18 en CPU'}
              </h3>
              <p class="body-6 text-[var(--studio-muted)]">
                {middleTruncate(activeJob.filename, 48)} · {formatBytes(activeJob.actual_size_bytes)}
                {phase === 'queued' && activeJob.queue_position
                  ? ` · posición #${activeJob.queue_position}`
                  : ''}
              </p>
            </div>
            <Badge tone="info" dot>
              {phase === 'queued' ? 'EN COLA' : 'ANALIZANDO'}
            </Badge>
          </div>
          <Skeleton class="h-44 w-full" />
          <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Skeleton class="h-20 w-full" />
            <Skeleton class="h-20 w-full" />
            <Skeleton class="h-20 w-full" />
            <Skeleton class="h-20 w-full" />
          </div>
        </div>
      {/if}

      {#if activeJob && activeJob.status === 'completed'}
        <!-- Cabecera del archivo activo -->
        <div
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] px-4 py-3"
        >
          <div class="min-w-0">
            <h3
              class="title-3 truncate font-semibold text-[var(--studio-text)]"
              title={activeJob.filename}
            >
              {middleTruncate(activeJob.filename, 56)}
            </h3>
            <p
              class="mt-0.5 font-mono text-xs text-[var(--studio-muted)] tabular-nums"
            >
              {formatSeconds(activeJob.audio?.duration_seconds)} ·
              {formatBytes(activeJob.actual_size_bytes)} ·
              {activeJob.audio
                ? `${activeJob.audio.original_sample_rate} Hz (${activeJob.audio.original_channels} ch)`
                : ''}
            </p>
          </div>

          <Badge
            tone={activeJob.short_clip
              ? 'info'
              : activeJob.windows_positive > 0
                ? 'target'
                : 'ok'}
            dot
          >
            {activeJob.short_clip
              ? 'Sin ventanas completas (< 3,0 s)'
              : activeJob.windows_positive > 0
                ? `${activeJob.windows_positive} ventana(s) con sirena`
                : 'Sin detecciones de sirena'}
          </Badge>
        </div>

        {#if activeJob.short_clip && activeJob.short_clip_message}
          <div
            role="status"
            class="rounded-xl border border-[var(--badge-info-border)] bg-[var(--badge-info-bg)] p-4 text-sm text-[var(--badge-info-text)]"
          >
            <p class="font-medium">
              Archivo por debajo de la ventana mínima del modelo
            </p>
            <p class="mt-1 text-xs opacity-95">
              {activeJob.short_clip_message}
            </p>
          </div>
        {/if}

        <!-- Consola de señal DAW (Forma de onda / Espectrograma + Transporte por ventana) -->
        <div
          class="overflow-hidden rounded-xl border border-[var(--studio-border)] bg-[var(--studio-bg)]"
        >
          <Tabs.Root bind:value={activeView}>
            <div
              class="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--studio-border)] bg-[var(--studio-panel)] px-4 py-2.5"
            >
              <Tabs.List
                class="inline-flex items-center gap-1 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-1"
                aria-label="Visualización de señal acústica"
              >
                <Tabs.Trigger
                  value="waveform"
                  class="cursor-pointer rounded-md px-3 py-1 text-xs font-medium text-[var(--studio-muted)] transition-colors data-[state=active]:bg-[var(--studio-raised)] data-[state=active]:text-[var(--studio-text)]"
                >
                  Forma de onda
                </Tabs.Trigger>
                <Tabs.Trigger
                  value="spectrogram"
                  class="cursor-pointer rounded-md px-3 py-1 text-xs font-medium text-[var(--studio-muted)] transition-colors data-[state=active]:bg-[var(--studio-raised)] data-[state=active]:text-[var(--studio-text)]"
                >
                  Espectrograma calculado
                </Tabs.Trigger>
              </Tabs.List>

              <div
                class="flex flex-wrap items-center gap-3 text-[11px] text-[var(--studio-muted)]"
              >
                <span class="inline-flex items-center gap-1.5">
                  <span
                    class="size-2.5 rounded-xs bg-[#f0c779]"
                    aria-hidden="true"
                  ></span>
                  Ventana EMERGENCY
                </span>
                <span class="hidden items-center gap-1.5 sm:inline-flex">
                  <span
                    class="size-2.5 rounded-xs bg-[var(--studio-accent)]"
                    aria-hidden="true"
                  ></span>
                  Señal WAV real
                </span>
              </div>
            </div>

            <div class="p-4">
              {#if loadingAudioVisuals && !waveformPeaks}
                <Skeleton class="h-[196px] w-full" />
              {:else}
                <Tabs.Content value="waveform">
                  <WaveformCanvas
                    peaks={waveformPeaks}
                    duration={displayDuration}
                    {currentTime}
                    windows={activeJob.windows}
                    selectedIndex={selectedWindowIndex}
                    theme={studioTheme}
                    onSeek={sec => seekTo(sec, true)}
                  />
                </Tabs.Content>

                <Tabs.Content value="spectrogram">
                  <SpectrogramCanvas
                    spectrogram={spectrogramData}
                    {currentTime}
                    windows={activeJob.windows}
                    selectedIndex={selectedWindowIndex}
                    onSeek={sec => seekTo(sec, true)}
                  />
                </Tabs.Content>
              {/if}
            </div>
          </Tabs.Root>

          <!-- Consola de transporte DAW (navegación paso a paso entre ventanas + reproducción sin autoplay) -->
          <div
            class="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--studio-border)] bg-[var(--studio-panel)] px-4 py-3"
          >
            <div class="flex flex-wrap items-center gap-2.5">
              {#if activeJob.windows.length > 1}
                <button
                  type="button"
                  class="flex size-9 cursor-pointer items-center justify-center rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] text-[var(--studio-text)] transition-colors hover:border-[var(--studio-accent)] disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Ventana temporal anterior"
                  title="Ventana anterior"
                  disabled={selectedWindowIndex === null || selectedWindowIndex <= 0}
                  onclick={() => stepWindow(-1)}
                >
                  <CaretLeft class="size-4" aria-hidden="true" />
                </button>
              {/if}

              <Button
                variant="primary"
                size="icon"
                class="rounded-full"
                aria-label={isPlaying ? 'Pausar audio' : 'Reproducir audio'}
                disabled={!audioSrc}
                onclick={() => void togglePlay()}
              >
                {#if isPlaying}
                  <Pause class="size-4" weight="fill" aria-hidden="true" />
                {:else}
                  <Play class="size-4" weight="fill" aria-hidden="true" />
                {/if}
              </Button>

              {#if activeJob.windows.length > 1}
                <button
                  type="button"
                  class="flex size-9 cursor-pointer items-center justify-center rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] text-[var(--studio-text)] transition-colors hover:border-[var(--studio-accent)] disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Ventana temporal siguiente"
                  title="Ventana siguiente"
                  disabled={selectedWindowIndex === null || selectedWindowIndex >= activeJob.windows.length - 1}
                  onclick={() => stepWindow(1)}
                >
                  <CaretRight class="size-4" aria-hidden="true" />
                </button>
              {/if}

              <div
                class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] px-3 py-1.5 font-mono text-xs text-[var(--studio-text)] tabular-nums"
              >
                {formatClock(currentTime)}
                <span class="text-[var(--studio-muted)]">/ {formatClock(displayDuration)}</span>
              </div>

              {#if selectedWindow}
                <span
                  class="hidden rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] px-2.5 py-1.5 font-mono text-[11px] text-[var(--studio-muted)] tabular-nums sm:inline-block"
                >
                  V{String(selectedWindow.index + 1).padStart(2, '0')} · {formatSeconds(selectedWindow.start_seconds)}–{formatSeconds(selectedWindow.end_seconds)}
                </span>
              {/if}
            </div>

            <span class="font-mono text-[11px] text-[var(--studio-muted)]">
              R2 GET temporal autorizado · sin autoplay
            </span>
          </div>
        </div>

        <MetricGrid job={activeJob} {selectedWindow} />

        {#if activeJob.windows.length > 0}
          <WindowScoreChart
            windows={activeJob.windows}
            threshold={activeJob.threshold ?? DOPPLER_DEFAULTS.threshold}
            selectedIndex={selectedWindowIndex}
            onSelect={handleSelectWindow}
          />

          <WindowTable
            windows={activeJob.windows}
            threshold={activeJob.threshold ?? DOPPLER_DEFAULTS.threshold}
            selectedIndex={selectedWindowIndex}
            onSelect={handleSelectWindow}
          />
        {/if}

        <TraceabilityPanel job={activeJob} />
      {/if}
    </div>
  </div>

  <div
    class="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--studio-border)] bg-[var(--studio-panel)] px-4 py-3 font-mono text-[11px] text-[var(--studio-muted)] sm:px-6"
  >
    <span>
      Las predicciones corresponden a ventanas solapadas de 3,0 s. No representan clasificación global validada ni certeza absoluta.
    </span>
    <span>DOPPLER / ESPECTRO</span>
  </div>
</div>

<ConfirmDeleteDialog
  bind:open={deleteDialogOpen}
  filename={activeJob?.filename ?? ''}
  busy={deletingJob}
  onConfirm={() => void handleConfirmDelete()}
  onCancel={() => {
    deleteDialogOpen = false
  }}
/>
