<script lang="ts">
  import Pulse from 'phosphor-svelte/lib/Pulse'

  import { Badge } from '@/components/ui/badge'
  import { Button } from '@/components/ui/button'
  import { formatBytes } from '@/helpers/format'
  import type { AdminOverview } from '@/helpers/maintenanceApi'

  interface Props {
    overview: AdminOverview
    probing: boolean
    onProbeNow: () => void
  }

  let { overview, probing, onProbeNow }: Props = $props()

  function statusTone(
    status: string
  ): 'ok' | 'target' | 'error' | 'info' | 'neutral' {
    if (status === 'healthy' || status === 'ok' || status === 'resolved') {
      return 'ok'
    }

    if (status === 'degraded' || status === 'warning') {
      return 'target'
    }

    if (
      status === 'unavailable' ||
      status === 'open' ||
      status === 'critical' ||
      status === 'error'
    ) {
      return 'error'
    }

    return 'neutral'
  }

  function fmtMs(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return '—'
    }

    return `${value.toFixed(1)} ms`
  }

  const componentCards = $derived([
    { label: 'API Rust (Axum)', data: overview.live.api },
    { label: 'SQLite (WAL)', data: overview.live.sqlite },
    { label: 'Inferencia PyTorch CPU', data: overview.live.inference },
    { label: 'Cloudflare R2 (privado)', data: overview.live.r2 }
  ])

  const latencyRows = $derived([
    { label: 'Espera en cola', data: overview.latencies.queue_wait },
    { label: 'Descarga desde R2', data: overview.latencies.r2_fetch },
    {
      label: 'Decodificación y Log-Mel',
      data: overview.latencies.decode_and_prepare
    },
    { label: 'Inferencia ResNet18 CPU', data: overview.latencies.inference },
    { label: 'Persistencia SQLite (commit)', data: overview.latencies.persist },
    { label: 'Total procesamiento API', data: overview.latencies.total_processing }
  ])
</script>

<div class="flex flex-col gap-6">
  <!-- Salud actual de componentes -->
  <section
    class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
  >
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="title-3 font-semibold text-[var(--studio-text)]">
          Salud de dependencias en vivo
        </h2>
        <p class="mt-0.5 font-mono text-xs text-[var(--studio-muted)]">
          Última verificación: {overview.live.checked_at} · Ready para tráfico:
          {overview.live.ready_for_traffic ? 'SÍ (HTTP 200)' : 'NO (HTTP 503)'}
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Badge tone={statusTone(overview.live.overall_status)} dot>
          Estado global: {overview.live.overall_status}
        </Badge>
        <Button
          variant="outline"
          size="sm"
          disabled={probing}
          onclick={onProbeNow}
        >
          <Pulse class="size-4" aria-hidden="true" />
          <span>{probing ? 'Sondeando…' : 'Ejecutar sonda ahora'}</span>
        </Button>
      </div>
    </div>

    <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {#each componentCards as comp (comp.label)}
        <div
          class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3.5"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-medium text-[var(--studio-text)]">
              {comp.label}
            </span>
            <Badge tone={statusTone(comp.data.status)} dot>
              {comp.data.status}
            </Badge>
          </div>
          <p class="mt-2 font-mono text-sm text-[var(--studio-text)] tabular-nums">
            {fmtMs(comp.data.latency_ms)}
          </p>
          {#if comp.data.detail}
            <p class="mt-1 text-[11px] text-[var(--studio-muted)]">
              {comp.data.detail}
            </p>
          {/if}
        </div>
      {/each}
    </div>
  </section>

  <!-- Contadores operativos desacoplados (30 días) y almacenamiento -->
  <div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
    <section
      class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
    >
      <h2 class="title-3 font-semibold text-[var(--studio-text)]">
        Contadores de trabajos ({overview.counters.window_days} días)
      </h2>
      <p class="mt-0.5 text-xs text-[var(--studio-muted)]">
        Historial desacoplado en SQLite que sobrevive a la purga de 24 h de archivos WAV.
      </p>
      <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <p class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Registrados
          </p>
          <p class="mt-1 font-mono text-xl font-semibold text-[var(--studio-text)] tabular-nums">
            {overview.counters.total_recorded}
          </p>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <p class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Completados
          </p>
          <p class="mt-1 font-mono text-xl font-semibold text-[#86d6b8] tabular-nums">
            {overview.counters.completed}
          </p>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <p class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Errores usuario
          </p>
          <p class="mt-1 font-mono text-xl font-semibold text-[#f0c779] tabular-nums">
            {overview.counters.user_validation_errors}
          </p>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <p class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Errores internos
          </p>
          <p class="mt-1 font-mono text-xl font-semibold text-[#f69d9d] tabular-nums">
            {overview.counters.internal_errors}
          </p>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <p class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Clips &lt; 3,0 s
          </p>
          <p class="mt-1 font-mono text-xl font-semibold text-[var(--studio-text)] tabular-nums">
            {overview.counters.short_clips}
          </p>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <p class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Activos (24 h)
          </p>
          <p class="mt-1 font-mono text-xl font-semibold text-[var(--studio-accent)] tabular-nums">
            {overview.counters.active_jobs_in_24h_table}
          </p>
        </div>
      </div>
    </section>

    <section
      class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
    >
      <h2 class="title-3 font-semibold text-[var(--studio-text)]">
        Cola, almacenamiento y configuración activa
      </h2>
      <p class="mt-0.5 text-xs text-[var(--studio-muted)]">
        Uso medido exclusivamente bajo el prefijo gestionado en R2 y volumen SQLite local.
      </p>
      <dl class="mt-4 grid grid-cols-1 gap-2.5 text-xs sm:grid-cols-2">
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Cola / Analizando
          </dt>
          <dd class="mt-1 font-mono text-sm text-[var(--studio-text)] tabular-nums">
            {overview.live.queue_depth ?? '—'} / {overview.live.analyzing_count ?? '—'}
            (máx {overview.monitoring_config.max_queue_depth})
          </dd>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            SQLite (db+wal+shm)
          </dt>
          <dd class="mt-1 font-mono text-sm text-[var(--studio-text)] tabular-nums">
            {formatBytes(overview.storage.sqlite_size_bytes)}
          </dd>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            R2 gestionado (prefijo)
          </dt>
          <dd class="mt-1 font-mono text-sm text-[var(--studio-text)] tabular-nums">
            {formatBytes(overview.storage.r2_managed_bytes)} · {overview.storage.r2_managed_objects ?? '—'} obj
          </dd>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Retenciones / Sonda
          </dt>
          <dd class="mt-1 font-mono text-sm text-[var(--studio-text)] tabular-nums">
            WAV {overview.monitoring_config.job_retention_hours} h · Hist {overview.monitoring_config.history_retention_days} d · {overview.monitoring_config.health_check_interval_seconds} s
          </dd>
        </div>
      </dl>
    </section>
  </div>

  <!-- Latencias por etapa y por duración -->
  <section
    class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
  >
    <h2 class="title-3 font-semibold text-[var(--studio-text)]">
      Latencias por etapa y por rango de duración
    </h2>
    <p class="mt-0.5 text-xs text-[var(--studio-muted)]">
      {overview.timing_boundary_note}
    </p>

    <div class="mt-4 overflow-x-auto">
      <table class="w-full min-w-[560px] border-collapse text-left text-xs">
        <thead>
          <tr class="border-b border-[var(--studio-border)] font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            <th class="py-2 pr-3">Etapa</th>
            <th class="py-2 pr-3">Muestras (n)</th>
            <th class="py-2 pr-3">p50</th>
            <th class="py-2 pr-3">p95</th>
            <th class="py-2">Media</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-[var(--studio-border)]/60 font-mono tabular-nums">
          {#each latencyRows as row (row.label)}
            <tr>
              <td class="py-2 pr-3 font-sans text-[var(--studio-text)]">
                {row.label}
              </td>
              <td class="py-2 pr-3 text-[var(--studio-muted)]">{row.data.n}</td>
              <td class="py-2 pr-3 text-[var(--studio-text)]">
                {fmtMs(row.data.p50_ms)}
              </td>
              <td class="py-2 pr-3 text-[var(--studio-text)]">
                {fmtMs(row.data.p95_ms)}
              </td>
              <td class="py-2 text-[var(--studio-muted)]">
                {fmtMs(row.data.mean_ms)}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    {#if overview.latency_by_duration_bucket.length > 0}
      <div class="mt-5 overflow-x-auto border-t border-[var(--studio-border)] pt-4">
        <p class="mb-2 font-mono text-[11px] text-[var(--studio-muted)] uppercase">
          Desglose por duración de audio
        </p>
        <table class="w-full min-w-[600px] border-collapse text-left text-xs">
          <thead>
            <tr class="border-b border-[var(--studio-border)] font-mono text-[10px] text-[var(--studio-muted)] uppercase">
              <th class="py-2 pr-3">Rango</th>
              <th class="py-2 pr-3">n</th>
              <th class="py-2 pr-3">R2 p50</th>
              <th class="py-2 pr-3">Prep p50</th>
              <th class="py-2 pr-3">Inf p50</th>
              <th class="py-2 pr-3">Inf p95</th>
              <th class="py-2">Total p50</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-[var(--studio-border)]/60 font-mono tabular-nums">
            {#each overview.latency_by_duration_bucket as b (b.bucket)}
              <tr>
                <td class="py-2 pr-3 text-[var(--studio-text)]">{b.bucket}</td>
                <td class="py-2 pr-3 text-[var(--studio-muted)]">{b.n}</td>
                <td class="py-2 pr-3">{fmtMs(b.r2_fetch_p50_ms)}</td>
                <td class="py-2 pr-3">{fmtMs(b.decode_prepare_p50_ms)}</td>
                <td class="py-2 pr-3">{fmtMs(b.inference_p50_ms)}</td>
                <td class="py-2 pr-3">{fmtMs(b.inference_p95_ms)}</td>
                <td class="py-2 text-[var(--studio-accent)]">
                  {fmtMs(b.total_processing_p50_ms)}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>

  <!-- Incidentes y bitácora de retención -->
  <div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
    <section
      class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
    >
      <h2 class="title-3 font-semibold text-[var(--studio-text)]">
        Incidentes operativos y recuperaciones
      </h2>
      <p class="mt-0.5 text-xs text-[var(--studio-muted)]">
        Se abre incidente tras {overview.monitoring_config.incident_failure_threshold} fallos consecutivos y se resuelve automáticamente al recuperarse el componente.
      </p>
      {#if overview.incidents.length === 0}
        <p class="mt-4 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3 text-xs text-[var(--studio-muted)]">
          Sin incidentes registrados en la ventana actual.
        </p>
      {:else}
        <ul class="mt-3 flex flex-col gap-2">
          {#each overview.incidents as inc (inc.id)}
            <li class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3 text-xs">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="font-mono font-medium text-[var(--studio-text)]">
                  {inc.component} · {inc.consecutive_failures} fallos
                </span>
                <Badge tone={statusTone(inc.status)}>{inc.status}</Badge>
              </div>
              <p class="mt-1 text-[var(--studio-muted)]">{inc.summary}</p>
              <p class="mt-1 font-mono text-[10px] text-[var(--studio-subtle)]">
                Abierto: {inc.opened_at}
                {inc.resolved_at ? ` · Resuelto: ${inc.resolved_at}` : ''}
              </p>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section
      class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
    >
      <h2 class="title-3 font-semibold text-[var(--studio-text)]">
        Ejecuciones de retención y limpieza
      </h2>
      <p class="mt-0.5 text-xs text-[var(--studio-muted)]">
        Registro automático de purgas de trabajos/audios 24 h y expiración de telemetría de 30 días.
      </p>
      {#if overview.retention_runs.length === 0}
        <p class="mt-4 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3 text-xs text-[var(--studio-muted)]">
          Todavía no se registraron ciclos de limpieza.
        </p>
      {:else}
        <ul class="mt-3 flex flex-col gap-2">
          {#each overview.retention_runs.slice(0, 8) as run (run.id)}
            <li class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3 font-mono text-[11px]">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="text-[var(--studio-text)]">{run.ran_at}</span>
                <Badge tone={statusTone(run.status)}>{run.status}</Badge>
              </div>
              <p class="mt-1 text-[var(--studio-muted)]">
                jobs={run.jobs_deleted} · r2_del={run.r2_objects_deleted} · r2_err={run.r2_errors} · hist_del={run.history_rows_deleted} · {run.duration_ms.toFixed(1)} ms
              </p>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>
</div>
