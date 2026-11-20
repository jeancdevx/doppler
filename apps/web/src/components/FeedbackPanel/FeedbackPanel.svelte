<script lang="ts">
  import ChatCircleText from 'phosphor-svelte/lib/ChatCircleText'
  import CheckCircle from 'phosphor-svelte/lib/CheckCircle'
  import PaperPlaneTilt from 'phosphor-svelte/lib/PaperPlaneTilt'
  import { toast } from 'svelte-sonner'

  import { Badge } from '@/components/ui/badge'
  import { Button } from '@/components/ui/button'
  import {
    type FeedbackReport,
    type FeedbackType,
    type JobDetail,
    createJobFeedback,
    listJobFeedback
  } from '@/helpers/api'
  import { formatSeconds } from '@/helpers/format'

  interface Props {
    job: JobDetail
    selectedWindowIndex: number | null
  }

  let { job, selectedWindowIndex }: Props = $props()

  let feedbackType = $state<FeedbackType>('false_alarm')
  let targetWindowIndex = $state<number | null>(null)
  let comment = $state('')
  let submitting = $state(false)
  let loadingReports = $state(false)
  let reports = $state.raw<FeedbackReport[]>([])
  let lastJobId = $state<string | null>(null)

  const requiresWindow = $derived(
    feedbackType === 'false_alarm' || feedbackType === 'missed_emergency'
  )

  const selectedWindowObj = $derived.by(() => {
    if (targetWindowIndex === null) {
      return null
    }

    return job.windows.find(w => w.index === targetWindowIndex) ?? null
  })

  $effect(() => {
    if (selectedWindowIndex !== null && job.windows.length > 0) {
      targetWindowIndex = selectedWindowIndex
    } else if (job.windows.length > 0 && targetWindowIndex === null) {
      targetWindowIndex = job.windows[0].index
    }
  })

  $effect(() => {
    if (job.job_id !== lastJobId) {
      lastJobId = job.job_id

      if (job.windows.length === 0 && requiresWindow) {
        feedbackType = 'technical_issue'
      }

      void loadReports(job.job_id)
    }
  })

  async function loadReports(jobId: string) {
    loadingReports = true

    try {
      reports = await listJobFeedback(jobId)
    } catch {
      reports = []
    } finally {
      loadingReports = false
    }
  }

  async function handleSubmit(event: SubmitEvent) {
    event.preventDefault()

    if (requiresWindow && targetWindowIndex === null) {
      toast.error(
        'Selecciona la ventana temporal específica para reportar una discrepancia de predicción.'
      )

      return
    }

    submitting = true

    try {
      const created = await createJobFeedback(job.job_id, {
        feedback_type: feedbackType,
        window_index: requiresWindow
          ? targetWindowIndex
          : (targetWindowIndex ?? null),
        comment: comment.trim() ? comment.trim() : null
      })

      reports = [created, ...reports]
      comment = ''
      toast.success(
        'Retroalimentación registrada. Queda pendiente de revisión humana.'
      )
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : 'No se pudo enviar el reporte de retroalimentación.'
      )
    } finally {
      submitting = false
    }
  }

  const FEEDBACK_TYPE_LABELS: Record<FeedbackType, string> = {
    false_alarm: 'Falsa alarma (no había sirena)',
    missed_emergency: 'Sirena no detectada',
    technical_issue: 'Problema técnico / audio',
    uncertain_or_other: 'Caso incierto u otro comentario'
  }

  const STATUS_LABELS: Record<string, string> = {
    received: 'Recibido',
    in_review: 'En revisión',
    confirmed: 'Confirmado',
    dismissed: 'Descartado',
    insufficient_evidence: 'Evidencia insuficiente',
    resolved: 'Resuelto'
  }

  function statusTone(
    status: string
  ): 'ok' | 'target' | 'error' | 'info' | 'neutral' {
    if (status === 'confirmed' || status === 'resolved') {
      return 'ok'
    }

    if (status === 'in_review') {
      return 'info'
    }

    if (status === 'insufficient_evidence') {
      return 'target'
    }

    return 'neutral'
  }
</script>

<section
  class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
  aria-labelledby="feedback-panel-heading"
>
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div class="flex items-start gap-2.5">
      <ChatCircleText
        class="mt-0.5 size-5 shrink-0 text-[var(--studio-accent)]"
        aria-hidden="true"
      />
      <div>
        <h4
          id="feedback-panel-heading"
          class="title-3 font-semibold text-[var(--studio-text)]"
        >
          Reportar discrepancia o retroalimentación
        </h4>
        <p class="mt-0.5 text-xs text-[var(--studio-muted)]">
          Los reportes se asocian a la ventana seleccionada y pasan a revisión humana; nunca modifican el modelo automáticamente.
        </p>
      </div>
    </div>

    <Badge tone="neutral">
      {reports.length} reporte{reports.length === 1 ? '' : 's'} en este análisis
    </Badge>
  </div>

  <form
    class="mt-4 grid grid-cols-1 gap-3.5 md:grid-cols-2"
    onsubmit={event => void handleSubmit(event)}
  >
    <div class="flex flex-col gap-1.5">
      <label
        for="doppler-feedback-type"
        class="font-mono text-[11px] tracking-[0.04em] text-[var(--studio-muted)] uppercase"
      >
        Tipo de reporte
      </label>
      <select
        id="doppler-feedback-type"
        bind:value={feedbackType}
        class="min-h-[40px] rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] px-3 py-2 text-sm text-[var(--studio-text)] focus:border-[var(--studio-accent)]"
      >
        <option value="false_alarm" disabled={job.windows.length === 0}>
          Falsa alarma (ventana marcada EMERGENCY sin sirena)
        </option>
        <option value="missed_emergency" disabled={job.windows.length === 0}>
          Sirena no detectada (ventana marcada NON_EMERGENCY)
        </option>
        <option value="technical_issue">
          Problema técnico (carga, reproducción o formato)
        </option>
        <option value="uncertain_or_other">
          Caso incierto u otro comentario general
        </option>
      </select>
    </div>

    <div class="flex flex-col gap-1.5">
      <label
        for="doppler-feedback-window"
        class="font-mono text-[11px] tracking-[0.04em] text-[var(--studio-muted)] uppercase"
      >
        Ventana temporal {requiresWindow ? '(obligatoria)' : '(opcional)'}
      </label>
      <select
        id="doppler-feedback-window"
        value={targetWindowIndex === null ? '' : String(targetWindowIndex)}
        onchange={event => {
          const val = (event.currentTarget as HTMLSelectElement).value

          targetWindowIndex = val === '' ? null : Number.parseInt(val, 10)
        }}
        class="min-h-[40px] rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] px-3 py-2 font-mono text-xs text-[var(--studio-text)] focus:border-[var(--studio-accent)]"
      >
        {#if !requiresWindow}
          <option value="">General del análisis (sin ventana específica)</option>
        {/if}
        {#each job.windows as win (win.index)}
          <option value={String(win.index)}>
            V{String(win.index + 1).padStart(2, '0')} · {formatSeconds(win.start_seconds)}–{formatSeconds(win.end_seconds)} · {win.label} ({win.score.toFixed(3)})
          </option>
        {/each}
      </select>
    </div>

    {#if selectedWindowObj && requiresWindow}
      <div
        class="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] px-3 py-2 font-mono text-[11px] text-[var(--studio-muted)] md:col-span-2"
      >
        <span class="text-[var(--studio-text)]">
          Ventana V{String(selectedWindowObj.index + 1).padStart(2, '0')}
        </span>
        <span>·</span>
        <span>
          {formatSeconds(selectedWindowObj.start_seconds)}–{formatSeconds(selectedWindowObj.end_seconds)}
        </span>
        <span>·</span>
        <span>Mostrado: {selectedWindowObj.label}</span>
        <span>·</span>
        <span>Score: {selectedWindowObj.score.toFixed(4)}</span>
        <span>·</span>
        <span>
          Umbral: {(job.threshold ?? 0.6547843813896179).toFixed(4)}
        </span>
      </div>
    {/if}

    <div class="flex flex-col gap-1.5 md:col-span-2">
      <div class="flex items-center justify-between gap-2">
        <label
          for="doppler-feedback-comment"
          class="font-mono text-[11px] tracking-[0.04em] text-[var(--studio-muted)] uppercase"
        >
          Contexto opcional (sonido de fondo, distancia, motivo)
        </label>
        <span class="font-mono text-[10px] text-[var(--studio-muted)] tabular-nums">
          {comment.length}/1000
        </span>
      </div>
      <textarea
        id="doppler-feedback-comment"
        bind:value={comment}
        maxlength={1000}
        rows={2}
        placeholder="Ej.: Era una alarma de vehículo estacionado, no una sirena de emergencia."
        class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] px-3 py-2 text-sm text-[var(--studio-text)] placeholder:text-[var(--studio-subtle)] focus:border-[var(--studio-accent)]"
      ></textarea>
    </div>

    <div
      class="flex flex-wrap items-center justify-between gap-3 md:col-span-2"
    >
      <p class="text-[11px] text-[var(--studio-muted)]">
        Nota: el audio WAV se elimina automáticamente a las 24 h; si el reporte se revisa después de ese plazo, solo queda el registro técnico sin audio.
      </p>

      <Button
        type="submit"
        variant="primary"
        size="sm"
        disabled={submitting || (requiresWindow && job.windows.length === 0)}
      >
        <PaperPlaneTilt class="size-4" aria-hidden="true" />
        <span>{submitting ? 'Enviando…' : 'Enviar reporte'}</span>
      </Button>
    </div>
  </form>

  {#if !loadingReports && reports.length > 0}
    <div class="mt-4 border-t border-[var(--studio-border)] pt-4">
      <p class="font-mono text-[11px] text-[var(--studio-muted)] uppercase">
        Reportes registrados en esta sesión
      </p>
      <ul class="mt-2.5 flex flex-col gap-2">
        {#each reports as rep (rep.id)}
          <li
            class="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] px-3 py-2.5 text-xs"
          >
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-medium text-[var(--studio-text)]">
                  {FEEDBACK_TYPE_LABELS[rep.feedback_type] ?? rep.feedback_type}
                </span>
                {#if rep.window_index !== null}
                  <span class="font-mono text-[11px] text-[var(--studio-accent)]">
                    V{String(rep.window_index + 1).padStart(2, '0')}
                    {#if rep.displayed_score !== null}
                      ({rep.displayed_score.toFixed(3)})
                    {/if}
                  </span>
                {/if}
              </div>
              {#if rep.comment}
                <p class="mt-1 text-[var(--studio-muted)]">{rep.comment}</p>
              {/if}
              {#if rep.resolution_note}
                <p
                  class="mt-1 flex items-center gap-1.5 font-mono text-[11px] text-[#86d6b8]"
                >
                  <CheckCircle class="size-3.5 shrink-0" aria-hidden="true" />
                  <span>Revisión: {rep.resolution_note}</span>
                </p>
              {/if}
            </div>
            <Badge tone={statusTone(rep.review_status)}>
              {STATUS_LABELS[rep.review_status] ?? rep.review_status}
            </Badge>
          </li>
        {/each}
      </ul>
    </div>
  {/if}
</section>
