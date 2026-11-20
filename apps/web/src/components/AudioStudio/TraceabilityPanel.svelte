<script lang="ts">
  import type { JobDetail } from '@/helpers/api'
  import { formatBytes, formatMs, formatSeconds, shortHash } from '@/helpers/format'

  interface Props {
    job: JobDetail
  }

  let { job }: Props = $props()
</script>

<details
  class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)]"
>
  <summary
    class="flex cursor-pointer items-center justify-between gap-4 px-4 py-3 text-xs font-medium text-[var(--studio-text)]"
  >
    <span class="font-mono">
      TRAZABILIDAD DEL ANÁLISIS · {job.run_id}
    </span>
    <span class="font-mono text-[11px] text-[var(--studio-muted)]">
      SHA-256 · Tiempos por etapa · Parámetros de audio
    </span>
  </summary>

  <div
    class="grid grid-cols-1 gap-4 border-t border-[var(--studio-border)] p-4 text-xs md:grid-cols-3"
  >
    <div class="flex flex-col gap-1.5">
      <h5 class="caption-4 font-mono text-[var(--studio-muted)]">
        IDENTIDAD Y CONTRATO
      </h5>
      <dl class="flex flex-col gap-1 font-mono text-[11px]">
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Audio SHA-256</dt>
          <dd class="text-[var(--studio-text)]" title={job.audio_sha256 ?? ''}>
            {shortHash(job.audio_sha256)}
          </dd>
        </div>
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Modelo SHA-256</dt>
          <dd class="text-[var(--studio-text)]" title={job.model_sha256 ?? ''}>
            {shortHash(job.model_sha256)}
          </dd>
        </div>
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Contrato</dt>
          <dd class="truncate text-[var(--studio-text)]" title={job.contract_sha256 ?? ''}>
            {job.contract_version ?? '—'}
          </dd>
        </div>
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Tipo de score</dt>
          <dd class="truncate text-[var(--studio-text)]">
            {job.score_type ?? '—'}
          </dd>
        </div>
      </dl>
    </div>

    <div class="flex flex-col gap-1.5">
      <h5 class="caption-4 font-mono text-[var(--studio-muted)]">
        CARACTERÍSTICAS DEL AUDIO
      </h5>
      <dl class="flex flex-col gap-1 font-mono text-[11px] tabular-nums">
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Tamaño real R2</dt>
          <dd class="text-[var(--studio-text)]">{formatBytes(job.actual_size_bytes)}</dd>
        </div>
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Origen / Preparado</dt>
          <dd class="text-[var(--studio-text)]">
            {job.audio
              ? `${job.audio.original_sample_rate} Hz (${job.audio.original_channels} ch) → ${job.audio.prepared_sample_rate} Hz mono`
              : '—'}
          </dd>
        </div>
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Duración / Cola descartada</dt>
          <dd class="text-[var(--studio-text)]">
            {job.audio
              ? `${formatSeconds(job.audio.duration_seconds)} / ${formatSeconds(job.audio.discarded_tail_seconds)}`
              : '—'}
          </dd>
        </div>
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Pico antes → después</dt>
          <dd class="text-[var(--studio-text)]">
            {job.audio
              ? `${job.audio.peak_before_normalization.toFixed(3)} → ${job.audio.peak_after_normalization.toFixed(3)}`
              : '—'}
          </dd>
        </div>
      </dl>
    </div>

    <div class="flex flex-col gap-1.5">
      <h5 class="caption-4 font-mono text-[var(--studio-muted)]">
        TIEMPOS MEDIDOS (VALIDACIÓN LOCAL)
      </h5>
      <dl class="flex flex-col gap-1 font-mono text-[11px] tabular-nums">
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Transferencia a R2</dt>
          <dd class="text-[var(--studio-text)]">{formatMs(job.timings.client_upload_ms)}</dd>
        </div>
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Espera en cola / Lectura R2</dt>
          <dd class="text-[var(--studio-text)]">
            {formatMs(job.timings.queue_wait_ms)} / {formatMs(job.timings.r2_fetch_ms)}
          </dd>
        </div>
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Preparación / Inferencia CPU</dt>
          <dd class="text-[var(--studio-text)]">
            {formatMs(job.timings.decode_and_prepare_ms)} / {formatMs(job.timings.inference_ms)}
          </dd>
        </div>
        <div class="flex justify-between gap-2">
          <dt class="text-[var(--studio-muted)]">Persistencia / Total servidor</dt>
          <dd class="text-[var(--studio-text)]">
            {formatMs(job.timings.persist_ms)} / {formatMs(job.timings.total_processing_ms)}
          </dd>
        </div>
      </dl>
    </div>
  </div>
</details>
