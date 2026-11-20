<script lang="ts">
  import { toast } from 'svelte-sonner'

  import { Badge } from '@/components/ui/badge'
  import { Button } from '@/components/ui/button'
  import type { FeedbackReport, FeedbackReviewStatus } from '@/helpers/api'
  import type { AdminFeedbackList } from '@/helpers/maintenanceApi'

  interface Props {
    data: AdminFeedbackList | null
    statusFilter: string
    onFilterChange: (status: string) => void
    onUpdateReport: (
      reportId: string,
      payload: {
        review_status: FeedbackReviewStatus
        verified_label?: string | null
        resolution_note?: string | null
      }
    ) => Promise<void>
  }

  let { data, statusFilter, onFilterChange, onUpdateReport }: Props = $props()

  let savingId = $state<string | null>(null)
  let draftStatus = $state<Record<string, FeedbackReviewStatus>>({})
  let draftLabel = $state<Record<string, string>>({})
  let draftNote = $state<Record<string, string>>({})

  function allowedNextStates(
    current: FeedbackReviewStatus
  ): FeedbackReviewStatus[] {
    if (current === 'received') {
      return ['in_review']
    }

    if (current === 'in_review') {
      return ['confirmed', 'dismissed', 'insufficient_evidence']
    }

    if (
      current === 'confirmed' ||
      current === 'dismissed' ||
      current === 'insufficient_evidence'
    ) {
      return ['resolved']
    }

    return []
  }

  async function saveTransition(report: FeedbackReport) {
    const nextOptions = allowedNextStates(report.review_status)
    const targetStatus = draftStatus[report.id] ?? nextOptions[0]

    if (!targetStatus) {
      return
    }

    savingId = report.id

    try {
      await onUpdateReport(report.id, {
        review_status: targetStatus,
        verified_label: draftLabel[report.id] || null,
        resolution_note: draftNote[report.id]?.trim() || null
      })
      toast.success(`Reporte ${report.id} actualizado a ${targetStatus}.`)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : 'No se pudo actualizar el reporte.'
      )
    } finally {
      savingId = null
    }
  }

  const STATUS_FILTERS = [
    { value: '', label: 'Todos' },
    { value: 'received', label: 'Recibidos' },
    { value: 'in_review', label: 'En revisión' },
    { value: 'confirmed', label: 'Confirmados' },
    { value: 'insufficient_evidence', label: 'Evidencia insuf.' },
    { value: 'resolved', label: 'Resueltos' }
  ]
</script>

<div class="flex flex-col gap-5">
  <!-- Métricas sobre muestra revisada -->
  <section
    class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h2 class="title-3 font-semibold text-[var(--studio-text)]">
          Métricas sobre muestra revisada (deduplicada por ventana)
        </h2>
        <p class="mt-0.5 text-xs text-[var(--studio-muted)]">
          {data?.metrics.methodology_note ??
            'Solo incluye ventanas revisadas con etiqueta verificada binaria. Nunca sustituye una evaluación balanceada global.'}
        </p>
      </div>
      <Badge
        tone={data?.metrics.status === 'available_biased_sample'
          ? 'target'
          : 'neutral'}
      >
        {data?.metrics.status === 'available_biased_sample'
          ? 'Muestra voluntaria sesgada'
          : 'No disponibles'}
      </Badge>
    </div>

    {#if !data || data.metrics.status === 'unavailable'}
      <p
        class="mt-3 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3 text-xs text-[var(--studio-muted)]"
      >
        <strong>Métricas no disponibles:</strong> existen {data?.metrics.total_reports ?? 0} reporte(s) en total y 0 ventanas verificadas con etiqueta binaria confirmada.
      </p>
    {:else}
      <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <p class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Ventanas verificadas
          </p>
          <p class="mt-1 font-mono text-lg font-semibold text-[var(--studio-text)] tabular-nums">
            {data.metrics.deduplicated_verified_windows}
          </p>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <p class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Conf. EMERGENCY
          </p>
          <p class="mt-1 font-mono text-lg font-semibold text-[#f0c779] tabular-nums">
            {data.metrics.confirmed_emergency}
          </p>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <p class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Conf. NON_EMERGENCY
          </p>
          <p class="mt-1 font-mono text-lg font-semibold text-[#86d6b8] tabular-nums">
            {data.metrics.confirmed_non_emergency}
          </p>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <p class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Acuerdo en muestra
          </p>
          <p class="mt-1 font-mono text-lg font-semibold text-[var(--studio-accent)] tabular-nums">
            {data.metrics.agreement_rate_on_verified_sample !== null
              ? `${(data.metrics.agreement_rate_on_verified_sample * 100).toFixed(1)}%`
              : '—'}
          </p>
        </div>
      </div>
    {/if}
  </section>

  <!-- Cola de revisión de reportes -->
  <section
    class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
  >
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h3 class="title-3 font-semibold text-[var(--studio-text)]">
        Bandeja de retroalimentación ({data?.reports.length ?? 0})
      </h3>
      <div class="flex flex-wrap gap-1.5">
        {#each STATUS_FILTERS as f (f.value)}
          <button
            type="button"
            class={[
              'cursor-pointer rounded-lg border px-2.5 py-1 text-xs transition-colors',
              statusFilter === f.value
                ? 'border-[var(--studio-accent)] bg-[var(--studio-raised)] text-[var(--studio-text)]'
                : 'border-[var(--studio-border)] bg-[var(--studio-bg)] text-[var(--studio-muted)] hover:text-[var(--studio-text)]'
            ]}
            onclick={() => onFilterChange(f.value)}
          >
            {f.label}
          </button>
        {/each}
      </div>
    </div>

    {#if !data || data.reports.length === 0}
      <p class="mt-4 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-4 text-xs text-[var(--studio-muted)]">
        No hay reportes que coincidan con el filtro seleccionado.
      </p>
    {:else}
      <ul class="mt-4 flex flex-col gap-3">
        {#each data.reports as rep (rep.id)}
          {@const nextStates = allowedNextStates(rep.review_status)}
          <li class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-bg)] p-4 text-xs">
            <div class="flex flex-wrap items-start justify-between gap-2">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="font-mono font-semibold text-[var(--studio-text)]">
                    {rep.id}
                  </span>
                  <Badge tone="info">{rep.feedback_type}</Badge>
                  <Badge tone={rep.audio_currently_available ? 'ok' : 'target'}>
                    {rep.audio_currently_available
                      ? 'Audio disponible (<24 h)'
                      : 'Audio expirado o eliminado'}
                  </Badge>
                </div>
                <p class="mt-1 font-mono text-[11px] text-[var(--studio-muted)]">
                  job={rep.job_id}
                  {#if rep.window_index !== null}
                    · V{String(rep.window_index + 1).padStart(2, '0')} · {rep.displayed_label ?? '—'} (score {rep.displayed_score?.toFixed(4) ?? '—'})
                  {:else}
                    · reporte general
                  {/if}
                </p>
              </div>
              <Badge tone={rep.review_status === 'resolved' ? 'ok' : 'neutral'}>
                {rep.review_status}
              </Badge>
            </div>

            {#if rep.comment}
              <p class="mt-2 rounded-lg bg-[var(--studio-panel)] p-2.5 text-[var(--studio-text)]">
                "{rep.comment}"
              </p>
            {/if}

            {#if rep.verified_label || rep.resolution_note}
              <p class="mt-2 font-mono text-[11px] text-[#86d6b8]">
                {rep.verified_label ? `Etiqueta verificada: ${rep.verified_label}` : ''}
                {rep.resolution_note ? ` · Nota: ${rep.resolution_note}` : ''}
              </p>
            {/if}

            {#if nextStates.length > 0}
              <div class="mt-3 grid grid-cols-1 gap-2 border-t border-[var(--studio-border)] pt-3 sm:grid-cols-4">
                <select
                  aria-label={`Siguiente estado para ${rep.id}`}
                  value={draftStatus[rep.id] ?? nextStates[0]}
                  onchange={e => {
                    draftStatus = {
                      ...draftStatus,
                      [rep.id]: (e.currentTarget as HTMLSelectElement)
                        .value as FeedbackReviewStatus
                    }
                  }}
                  class="min-h-[36px] rounded-lg border border-[var(--studio-border)] bg-[var(--studio-panel)] px-2.5 text-xs text-[var(--studio-text)]"
                >
                  {#each nextStates as st (st)}
                    <option value={st}>{st}</option>
                  {/each}
                </select>

                <select
                  aria-label={`Etiqueta verificada para ${rep.id}`}
                  value={draftLabel[rep.id] ?? rep.verified_label ?? ''}
                  onchange={e => {
                    draftLabel = {
                      ...draftLabel,
                      [rep.id]: (e.currentTarget as HTMLSelectElement).value
                    }
                  }}
                  class="min-h-[36px] rounded-lg border border-[var(--studio-border)] bg-[var(--studio-panel)] px-2.5 text-xs text-[var(--studio-text)]"
                >
                  <option value="">Sin etiqueta verificada</option>
                  <option value="EMERGENCY">EMERGENCY</option>
                  <option value="NON_EMERGENCY">NON_EMERGENCY</option>
                  <option value="UNCERTAIN">UNCERTAIN</option>
                </select>

                <input
                  type="text"
                  placeholder="Nota de resolución (opcional)"
                  value={draftNote[rep.id] ?? rep.resolution_note ?? ''}
                  oninput={e => {
                    draftNote = {
                      ...draftNote,
                      [rep.id]: (e.currentTarget as HTMLInputElement).value
                    }
                  }}
                  class="min-h-[36px] rounded-lg border border-[var(--studio-border)] bg-[var(--studio-panel)] px-2.5 text-xs text-[var(--studio-text)]"
                />

                <Button
                  variant="outline"
                  size="sm"
                  disabled={savingId === rep.id}
                  onclick={() => void saveTransition(rep)}
                >
                  {savingId === rep.id ? 'Guardando…' : 'Aplicar transición'}
                </Button>
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>
</div>
