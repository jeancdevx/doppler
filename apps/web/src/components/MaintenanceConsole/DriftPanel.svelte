<script lang="ts">
  import ChartLineUp from 'phosphor-svelte/lib/ChartLineUp'
  import Warning from 'phosphor-svelte/lib/Warning'

  import { Badge } from '@/components/ui/badge'
  import { Button } from '@/components/ui/button'
  import type { DriftStatusResponse } from '@/helpers/maintenanceApi'

  interface Props {
    drift: DriftStatusResponse | null
    evaluating: boolean
    onEvaluate: () => void
  }

  let { drift, evaluating, onEvaluate }: Props = $props()

  const inputFeatures = $derived(
    drift?.latest_evaluation?.features.filter(f =>
      f.group.startsWith('input')
    ) ?? []
  )
  const outputFeatures = $derived(
    drift?.latest_evaluation?.features.filter(f =>
      f.group.startsWith('output')
    ) ?? []
  )

  function statusTone(
    status: string
  ): 'ok' | 'target' | 'error' | 'info' | 'neutral' {
    if (status === 'no_alert' || status === 'ok') {
      return 'ok'
    }

    if (status === 'drift_detected' || status === 'alert') {
      return 'target'
    }

    if (status === 'evaluation_error') {
      return 'error'
    }

    return 'info'
  }

  function repLabel(rep: string): string {
    if (rep === 'representative_real_corpus') {
      return 'Corpus real representativo'
    }

    if (rep === 'synthetic_demo') {
      return 'Referencia sintética de demostración (pendiente corpus real)'
    }

    return 'Referencia representativa pendiente'
  }
</script>

<div class="flex flex-col gap-5">
  <!-- Aviso explícito de procedencia / representatividad -->
  <div
    class="flex items-start gap-3 rounded-xl border border-[var(--badge-target-border)] bg-[var(--badge-target-bg)] p-4 text-xs text-[var(--badge-target-text)]"
  >
    <Warning class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
    <div class="min-w-0">
      <p class="font-semibold">
        Estado de representatividad: {repLabel(drift?.representative_status ?? 'pending_representative_corpus')}
      </p>
      <p class="mt-1 opacity-95">
        {drift?.latest_evaluation?.warning_note ??
          'El monitoreo separa señales de drift de entrada (audio/espectrograma) y de salida (scores/tasa positiva). Sin corpus real congelado, las alertas tienen alcance metodológico y no equivalen a validación de producción.'}
      </p>
    </div>
  </div>

  <!-- Referencia congelada activa -->
  <section
    class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
  >
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="title-3 font-semibold text-[var(--studio-text)]">
          Referencia congelada y evaluación de drift
        </h2>
        <p class="mt-0.5 text-xs text-[var(--studio-muted)]">
          Unidad de observación: archivo WAV (evitando dependencia entre ventanas solapadas).
        </p>
      </div>
      <Button
        variant="primary"
        size="sm"
        disabled={evaluating}
        onclick={onEvaluate}
      >
        <ChartLineUp class="size-4" aria-hidden="true" />
        <span>{evaluating ? 'Evaluando…' : 'Evaluar drift ahora'}</span>
      </Button>
    </div>

    {#if drift?.active_reference}
      <dl class="mt-4 grid grid-cols-1 gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Referencia activa
          </dt>
          <dd class="mt-1 font-medium text-[var(--studio-text)]">
            {drift.active_reference.name} ({drift.active_reference.version})
          </dd>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Tamaño y grupos
          </dt>
          <dd class="mt-1 font-mono text-[var(--studio-text)]">
            {drift.active_reference.file_count} archivos · {drift.active_reference.source_group_count} grupo(s) · mín {drift.active_reference.min_observations} obs
          </dd>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Extractor / Contrato
          </dt>
          <dd class="mt-1 font-mono text-[var(--studio-text)]">
            {drift.active_reference.extraction_version} · v{drift.active_reference.contract_version ?? '—'}
          </dd>
        </div>
        <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
          <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
            Último estado
          </dt>
          <dd class="mt-1">
            {#if drift.latest_evaluation}
              <Badge tone={statusTone(drift.latest_evaluation.status)} dot>
                {drift.latest_evaluation.status} (n={drift.latest_evaluation.sample_count})
              </Badge>
            {:else}
              <Badge tone="neutral">Sin evaluar</Badge>
            {/if}
          </dd>
        </div>
      </dl>
    {:else}
      <p class="mt-4 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3.5 text-xs text-[var(--studio-muted)]">
        No hay ninguna referencia de drift importada todavía. El estado operativo se reporta explícitamente como <span class="font-mono text-[var(--studio-text)]">no_reference</span>.
      </p>
    {/if}

    {#if drift?.latest_evaluation}
      <p class="mt-4 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3 text-xs text-[var(--studio-text)]">
        <strong>Resumen ({drift.latest_evaluation.evaluated_at}):</strong>
        {drift.latest_evaluation.summary}
      </p>
    {/if}
  </section>

  <!-- Drift de entrada vs Drift de salida -->
  {#if inputFeatures.length > 0 || outputFeatures.length > 0}
    <div class="grid grid-cols-1 gap-5">
      <section
        class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="title-3 font-semibold text-[var(--studio-text)]">
            Drift de entrada (características acústicas y de preprocesamiento)
          </h3>
          <Badge
            tone={drift?.latest_evaluation?.input_drift_detected
              ? 'target'
              : 'ok'}
          >
            {drift?.latest_evaluation?.input_drift_detected
              ? 'Alerta de entrada'
              : 'Sin alerta de entrada'}
          </Badge>
        </div>

        <div class="mt-3 overflow-x-auto">
          <table class="w-full min-w-[640px] border-collapse text-left text-xs">
            <thead>
              <tr class="border-b border-[var(--studio-border)] font-mono text-[10px] text-[var(--studio-muted)] uppercase">
                <th class="py-2 pr-3">Variable</th>
                <th class="py-2 pr-3">Método</th>
                <th class="py-2 pr-3">Media ref / obs</th>
                <th class="py-2 pr-3">Estadístico norm.</th>
                <th class="py-2 pr-3">Umbral</th>
                <th class="py-2">Estado</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-[var(--studio-border)]/60 font-mono tabular-nums">
              {#each inputFeatures as feat (feat.feature)}
                <tr>
                  <td class="py-2 pr-3 text-[var(--studio-text)]">
                    {feat.feature}
                  </td>
                  <td class="py-2 pr-3 text-[var(--studio-muted)]">
                    {feat.method}
                  </td>
                  <td class="py-2 pr-3 text-[var(--studio-muted)]">
                    {feat.ref_mean !== null ? feat.ref_mean.toFixed(3) : '—'} / {feat.obs_mean !== null ? feat.obs_mean.toFixed(3) : '—'}
                  </td>
                  <td class="py-2 pr-3 text-[var(--studio-text)]">
                    {feat.normalized_statistic !== null
                      ? feat.normalized_statistic.toFixed(3)
                      : '—'}
                  </td>
                  <td class="py-2 pr-3 text-[var(--studio-muted)]">
                    {feat.threshold.toFixed(3)}
                  </td>
                  <td class="py-2">
                    <Badge tone={statusTone(feat.status)}>{feat.status}</Badge>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>

      <section
        class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="title-3 font-semibold text-[var(--studio-text)]">
            Drift de salida (distribución de scores sigmoides y tasa positiva)
          </h3>
          <Badge
            tone={drift?.latest_evaluation?.output_drift_detected
              ? 'target'
              : 'ok'}
          >
            {drift?.latest_evaluation?.output_drift_detected
              ? 'Alerta de salida'
              : 'Sin alerta de salida'}
          </Badge>
        </div>

        <div class="mt-3 overflow-x-auto">
          <table class="w-full min-w-[640px] border-collapse text-left text-xs">
            <thead>
              <tr class="border-b border-[var(--studio-border)] font-mono text-[10px] text-[var(--studio-muted)] uppercase">
                <th class="py-2 pr-3">Variable</th>
                <th class="py-2 pr-3">Método</th>
                <th class="py-2 pr-3">Media ref / obs</th>
                <th class="py-2 pr-3">Estadístico norm.</th>
                <th class="py-2 pr-3">Umbral</th>
                <th class="py-2">Estado</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-[var(--studio-border)]/60 font-mono tabular-nums">
              {#each outputFeatures as feat (feat.feature)}
                <tr>
                  <td class="py-2 pr-3 text-[var(--studio-text)]">
                    {feat.feature}
                  </td>
                  <td class="py-2 pr-3 text-[var(--studio-muted)]">
                    {feat.method}
                  </td>
                  <td class="py-2 pr-3 text-[var(--studio-muted)]">
                    {feat.ref_mean !== null ? feat.ref_mean.toFixed(3) : '—'} / {feat.obs_mean !== null ? feat.obs_mean.toFixed(3) : '—'}
                  </td>
                  <td class="py-2 pr-3 text-[var(--studio-text)]">
                    {feat.normalized_statistic !== null
                      ? feat.normalized_statistic.toFixed(3)
                      : '—'}
                  </td>
                  <td class="py-2 pr-3 text-[var(--studio-muted)]">
                    {feat.threshold.toFixed(3)}
                  </td>
                  <td class="py-2">
                    <Badge tone={statusTone(feat.status)}>{feat.status}</Badge>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  {/if}
</div>
