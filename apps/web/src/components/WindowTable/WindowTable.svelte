<script lang="ts">
  import { Badge } from '@/components/ui/badge'
  import type { WindowPrediction } from '@/helpers/api'
  import { formatScore, formatSeconds } from '@/helpers/format'

  interface Props {
    windows: WindowPrediction[]
    threshold: number
    selectedIndex: number | null
    onSelect: (index: number, seekAudio: boolean) => void
  }

  let { windows, threshold, selectedIndex, onSelect }: Props = $props()

  let filter: 'all' | 'EMERGENCY' | 'NON_EMERGENCY' = $state('all')

  let filteredWindows = $derived(
    filter === 'all' ? windows : windows.filter(w => w.label === filter)
  )

  let emergencyCount = $derived(
    windows.filter(w => w.label === 'EMERGENCY').length
  )
</script>

<div
  class="overflow-hidden rounded-xl border border-[var(--studio-border)] bg-[var(--studio-bg)]"
>
  <div
    class="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--studio-border)] bg-[var(--studio-panel)] px-4 py-3"
  >
    <div>
      <h4 class="title-3 text-[var(--studio-text)]">
        Inspector de ventanas temporales
      </h4>
      <p class="text-xs text-[var(--studio-muted)]">
        Haz clic en cualquier ventana para fijar su selección y situar el cursor de audio en su inicio exacto.
      </p>
    </div>

    <div
      class="inline-flex rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-1"
      role="group"
      aria-label="Filtrar ventanas por clase"
    >
      <button
        type="button"
        class={[
          'cursor-pointer rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
          filter === 'all'
            ? 'bg-[var(--studio-raised)] text-[var(--studio-text)]'
            : 'text-[var(--studio-muted)] hover:text-[var(--studio-text)]'
        ]}
        onclick={() => {
          filter = 'all'
        }}
      >
        Todas ({windows.length})
      </button>
      <button
        type="button"
        class={[
          'cursor-pointer rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
          filter === 'EMERGENCY'
            ? 'bg-[var(--studio-raised)] text-[var(--studio-text)]'
            : 'text-[var(--studio-muted)] hover:text-[var(--studio-text)]'
        ]}
        onclick={() => {
          filter = 'EMERGENCY'
        }}
      >
        Sirena ({emergencyCount})
      </button>
      <button
        type="button"
        class={[
          'cursor-pointer rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
          filter === 'NON_EMERGENCY'
            ? 'bg-[var(--studio-raised)] text-[var(--studio-text)]'
            : 'text-[var(--studio-muted)] hover:text-[var(--studio-text)]'
        ]}
        onclick={() => {
          filter = 'NON_EMERGENCY'
        }}
      >
        Sin detección ({windows.length - emergencyCount})
      </button>
    </div>
  </div>

  {#if filteredWindows.length === 0}
    <div class="p-6 text-center text-sm text-[var(--studio-muted)]">
      No hay ventanas que coincidan con el filtro seleccionado.
    </div>
  {:else}
    <div class="max-h-[320px] overflow-auto">
      <table class="w-full border-collapse text-left text-xs">
        <thead
          class="sticky top-0 z-10 border-b border-[var(--studio-border)] bg-[var(--studio-bg)] font-mono text-[10px] tracking-[0.06em] text-[var(--studio-muted)] uppercase"
        >
          <tr>
            <th class="px-3.5 py-2.5 font-medium">#</th>
            <th class="px-3.5 py-2.5 font-medium">Intervalo (3,0 s)</th>
            <th class="px-3.5 py-2.5 font-medium">Clase</th>
            <th class="px-3.5 py-2.5 font-medium">Score</th>
            <th class="hidden px-3.5 py-2.5 font-medium md:table-cell">
              Margen Δ
            </th>
            <th class="hidden px-3.5 py-2.5 font-medium sm:table-cell">
              Referencia umbral ({formatScore(threshold)})
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-[var(--studio-border)]/80">
          {#each filteredWindows as win (win.index)}
            {@const active = selectedIndex === win.index}
            {@const isEmergency = win.label === 'EMERGENCY'}
            <tr
              data-window-index={win.index}
              data-selected={active ? 'true' : 'false'}
              aria-selected={active}
              class={[
                'cursor-pointer transition-colors',
                active
                  ? 'bg-[var(--studio-raised)]'
                  : 'hover:bg-[var(--studio-panel)]/70'
              ]}
              onclick={() => onSelect(win.index, true)}
            >
              <td
                class="relative px-3.5 py-2.5 font-mono text-[var(--studio-muted)] tabular-nums"
              >
                {#if active}
                  <span
                    class={[
                      'absolute inset-y-1 left-0 w-1 rounded-r-full',
                      isEmergency ? 'bg-[#f0c779]' : 'bg-[var(--studio-accent)]'
                    ]}
                    aria-hidden="true"
                  ></span>
                {/if}
                <span class:text-[var(--studio-text)]={active} class:font-semibold={active}>
                  {String(win.index + 1).padStart(2, '0')}
                </span>
              </td>
              <td
                class="px-3.5 py-2.5 font-mono text-[var(--studio-text)] whitespace-nowrap tabular-nums"
              >
                <button
                  type="button"
                  class="cursor-pointer text-left underline-offset-4 hover:underline"
                  aria-pressed={active}
                  onclick={event => {
                    event.stopPropagation()
                    onSelect(win.index, true)
                  }}
                >
                  {formatSeconds(win.start_seconds)} — {formatSeconds(win.end_seconds)}
                </button>
              </td>
              <td class="px-3.5 py-2.5">
                <Badge tone={isEmergency ? 'target' : 'neutral'} dot={isEmergency}>
                  {isEmergency ? 'EMERGENCY' : 'NON_EMERGENCY'}
                </Badge>
              </td>
              <td
                class="px-3.5 py-2.5 font-mono font-semibold text-[var(--studio-text)] tabular-nums"
              >
                {formatScore(win.score)}
              </td>
              <td
                class={[
                  'hidden px-3.5 py-2.5 font-mono tabular-nums md:table-cell',
                  win.margin_vs_threshold >= 0
                    ? 'text-[var(--badge-target-text)]'
                    : 'text-[var(--studio-muted)]'
                ]}
              >
                {win.margin_vs_threshold >= 0 ? '+' : ''}{formatScore(win.margin_vs_threshold)}
              </td>
              <td class="hidden px-3.5 py-2.5 sm:table-cell">
                <div
                  class="relative h-2 w-36 overflow-hidden rounded-full bg-[var(--studio-panel)]"
                >
                  <div
                    class={[
                      'h-full rounded-full',
                      isEmergency ? 'bg-[#f0c779]' : 'bg-[var(--studio-accent)]'
                    ]}
                    style:width={`${Math.round(win.score * 100)}%`}
                  ></div>
                  <div
                    class="absolute top-0 bottom-0 w-0.5 bg-[var(--studio-text)] opacity-85"
                    style:left={`${threshold * 100}%`}
                    title={`Umbral ${formatScore(threshold)}`}
                  ></div>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
