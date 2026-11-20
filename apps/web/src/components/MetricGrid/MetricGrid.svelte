<script lang="ts">
  import type { JobDetail, WindowPrediction } from '@/helpers/api'
  import { formatScore, formatSeconds } from '@/helpers/format'

  interface Props {
    job: JobDetail
    selectedWindow: WindowPrediction | null
  }

  let { job, selectedWindow }: Props = $props()

  let threshold = $derived(job.threshold ?? 0.6547843813896179)
  let isEmergency = $derived(selectedWindow?.label === 'EMERGENCY')
  let deltaLabel = $derived(
    selectedWindow
      ? `${selectedWindow.margin_vs_threshold >= 0 ? '+' : ''}${formatScore(selectedWindow.margin_vs_threshold)}`
      : '—'
  )
</script>

<div
  class="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4"
  aria-live="polite"
>
  <!-- Tarjeta 1: Diagnóstico de la ventana activa -->
  <div
    class={[
      'relative flex min-w-0 flex-col justify-between overflow-hidden rounded-xl border bg-[var(--studio-panel)] p-4',
      isEmergency
        ? 'border-[#f0c779]/65'
        : 'border-[var(--studio-border)]'
    ]}
  >
    <div
      class={[
        'pointer-events-none absolute inset-x-0 top-0 h-0.5',
        isEmergency ? 'bg-[#f0c779]' : 'bg-[var(--studio-accent)]/60'
      ]}
      aria-hidden="true"
    ></div>

    <div class="flex items-center justify-between gap-2">
      <span class="caption-4 font-mono text-[var(--studio-muted)]">
        VENTANA SELECCIONADA
      </span>
      {#if selectedWindow}
        <span
          class="rounded bg-[var(--studio-bg)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--studio-text)] tabular-nums"
        >
          #{String(selectedWindow.index + 1).padStart(2, '0')}
        </span>
      {/if}
    </div>

    {#if selectedWindow}
      <p
        class={[
          'mt-2.5 text-base font-semibold leading-snug',
          isEmergency
            ? 'text-[var(--badge-target-text)]'
            : 'text-[var(--studio-text)]'
        ]}
      >
        {isEmergency
          ? 'Sirena detectada en esta ventana'
          : 'Sin detección en esta ventana'}
      </p>
      <p
        class="mt-1.5 font-mono text-xs text-[var(--studio-muted)] tabular-nums"
      >
        {formatSeconds(selectedWindow.start_seconds)} a {formatSeconds(selectedWindow.end_seconds)}
        · {selectedWindow.label}
      </p>
    {:else}
      <p class="mt-2.5 text-base font-medium text-[var(--studio-muted)]">
        Sin ventanas
      </p>
      <p class="mt-1.5 text-xs text-[var(--studio-muted)]">
        {job.short_clip ? 'Audio menor de 3,0 s' : 'Selecciona una ventana'}
      </p>
    {/if}
  </div>

  <!-- Tarjeta 2: Score sigmoide + micro-barra contra umbral -->
  <div
    class="flex min-w-0 flex-col justify-between rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4"
  >
    <div class="flex items-center justify-between gap-2">
      <span class="caption-4 font-mono text-[var(--studio-muted)]">
        SCORE SIGMOIDE
      </span>
      <span
        class="font-mono text-[11px] text-[var(--studio-muted)] tabular-nums"
      >
        Δ {deltaLabel}
      </span>
    </div>

    <p
      class="mt-2 font-mono text-2xl font-medium text-[var(--studio-text)] tabular-nums"
    >
      {selectedWindow ? formatScore(selectedWindow.score) : '—'}
    </p>

    <div class="mt-2">
      {#if selectedWindow}
        <div
          class="relative h-1.5 w-full overflow-hidden rounded-full bg-[var(--studio-bg)]"
          aria-hidden="true"
        >
          <div
            class={[
              'h-full rounded-full',
              isEmergency ? 'bg-[#f0c779]' : 'bg-[var(--studio-accent)]'
            ]}
            style:width={`${Math.round(selectedWindow.score * 100)}%`}
          ></div>
          <div
            class="absolute top-0 bottom-0 w-0.5 bg-[var(--studio-text)]"
            style:left={`${threshold * 100}%`}
          ></div>
        </div>
      {/if}
      <p class="mt-1.5 text-[11px] text-[var(--studio-muted)] tabular-nums">
        Umbral {formatScore(threshold)} · no es probabilidad calibrada
      </p>
    </div>
  </div>

  <!-- Tarjeta 3: Conteo de ventanas solapadas -->
  <div
    class="flex min-w-0 flex-col justify-between rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4"
  >
    <span class="caption-4 font-mono text-[var(--studio-muted)]">
      VENTANAS POSITIVAS
    </span>
    <p
      class="mt-2 font-mono text-2xl font-medium text-[var(--studio-text)] tabular-nums"
    >
      {job.windows_positive}
      <span class="text-sm font-normal text-[var(--studio-muted)]">
        / {job.windows_total} analizadas
      </span>
    </p>
    <p class="mt-1.5 text-[11px] text-[var(--studio-muted)]">
      Bloques de 3,0 s con salto de 1,5 s (solapamiento 50 %)
    </p>
  </div>

  <!-- Tarjeta 4: Cobertura temporal unida derivada -->
  <div
    class="flex min-w-0 flex-col justify-between rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4"
  >
    <span class="caption-4 font-mono text-[var(--studio-muted)]">
      COBERTURA UNIDA DERIVADA
    </span>
    <p
      class="mt-2 font-mono text-2xl font-medium text-[var(--studio-text)] tabular-nums"
    >
      {formatSeconds(job.positive_coverage_seconds)}
    </p>
    <p class="mt-1.5 text-[11px] text-[var(--studio-muted)]">
      {job.merged_positive_intervals.length === 0
        ? 'Sin intervalos positivos unidos'
        : `${job.merged_positive_intervals.length} intervalo(s) derivado(s) de ventanas solapadas`}
    </p>
  </div>
</div>
