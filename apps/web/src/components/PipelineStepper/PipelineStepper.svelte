<script lang="ts">
  import CheckCircle from 'phosphor-svelte/lib/CheckCircle'
  import CircleNotch from 'phosphor-svelte/lib/CircleNotch'
  import WarningCircle from 'phosphor-svelte/lib/WarningCircle'

  import type { JobTimings } from '@/helpers/api'
  import { formatMs } from '@/helpers/format'

  export type StudioPhase =
    | 'idle'
    | 'validating'
    | 'uploading'
    | 'queued'
    | 'analyzing'
    | 'completed'
    | 'error'

  interface Props {
    phase: StudioPhase
    uploadPercent?: number
    queuePosition?: number | null
    timings?: JobTimings | null
  }

  let {
    phase,
    uploadPercent = 0,
    queuePosition = null,
    timings = null
  }: Props = $props()

  const steps: { id: StudioPhase; code: string; label: string }[] = [
    { id: 'validating', code: '01', label: 'Validando' },
    { id: 'uploading', code: '02', label: 'Subida R2' },
    { id: 'queued', code: '03', label: 'En cola' },
    { id: 'analyzing', code: '04', label: 'ResNet18' },
    { id: 'completed', code: '05', label: 'Completado' }
  ]

  const order: Record<StudioPhase, number> = {
    idle: -1,
    validating: 0,
    uploading: 1,
    queued: 2,
    analyzing: 3,
    completed: 4,
    error: -2
  }

  function stepState(
    stepId: StudioPhase
  ): 'done' | 'active' | 'pending' | 'error' {
    if (phase === 'error') {
      return 'error'
    }

    const current = order[phase]
    const target = order[stepId]

    if (current < 0) {
      return 'pending'
    }

    if (current > target || (phase === 'completed' && stepId === 'completed')) {
      return 'done'
    }

    if (current === target) {
      return 'active'
    }

    return 'pending'
  }

  function stepMeta(stepId: StudioPhase): string {
    if (stepId === 'uploading') {
      if (phase === 'uploading') {
        return `${uploadPercent} %`
      }

      if (
        timings?.client_upload_ms !== null &&
        timings?.client_upload_ms !== undefined
      ) {
        return formatMs(timings.client_upload_ms)
      }
    }

    if (stepId === 'queued') {
      if (phase === 'queued' && queuePosition) {
        return `#${queuePosition}`
      }

      if (
        timings?.queue_wait_ms !== null &&
        timings?.queue_wait_ms !== undefined
      ) {
        return formatMs(timings.queue_wait_ms)
      }
    }

    if (stepId === 'analyzing') {
      const sum =
        (timings?.r2_fetch_ms ?? 0) +
        (timings?.decode_and_prepare_ms ?? 0) +
        (timings?.inference_ms ?? 0)

      if (sum > 0 && phase === 'completed') {
        return formatMs(sum)
      }
    }

    if (stepId === 'completed' && timings?.total_processing_ms) {
      return formatMs(timings.total_processing_ms)
    }

    return ''
  }
</script>

<ol
  class="grid grid-cols-2 gap-2 sm:grid-cols-5"
  aria-label="Etapas del análisis"
>
  {#each steps as step (step.id)}
    {@const state = stepState(step.id)}
    {@const meta = stepMeta(step.id)}
    <li
      class={[
        'flex min-w-0 items-center gap-2.5 rounded-xl border px-3 py-2.5 text-xs transition-colors',
        state === 'done'
          ? 'border-[var(--badge-ok-border)] bg-[var(--badge-ok-bg)] text-[var(--badge-ok-text)]'
          : state === 'active'
            ? 'border-[var(--studio-accent)] bg-[var(--studio-raised)] text-[var(--studio-text)]'
            : state === 'error'
              ? 'border-[var(--badge-error-border)] bg-[var(--badge-error-bg)] text-[var(--badge-error-text)]'
              : 'border-[var(--studio-border)] bg-[var(--studio-panel)] text-[var(--studio-muted)]'
      ]}
      aria-current={state === 'active' ? 'step' : undefined}
    >
      {#if state === 'done'}
        <CheckCircle class="size-4 shrink-0" weight="fill" aria-hidden="true" />
      {:else if state === 'active'}
        <CircleNotch class="size-4 shrink-0 animate-spin" aria-hidden="true" />
      {:else if state === 'error'}
        <WarningCircle class="size-4 shrink-0" aria-hidden="true" />
      {:else}
        <span
          class="font-mono text-[10px] opacity-65 tabular-nums"
          aria-hidden="true"
        >
          {step.code}
        </span>
      {/if}
      <div class="min-w-0 flex-1">
        <span class="block truncate font-medium">{step.label}</span>
        {#if meta}
          <span
            class="block truncate font-mono text-[10px] opacity-85 tabular-nums"
          >
            {meta}
          </span>
        {/if}
      </div>
    </li>
  {/each}
</ol>
