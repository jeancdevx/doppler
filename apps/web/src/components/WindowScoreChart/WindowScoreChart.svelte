<script lang="ts">
  import type { WindowPrediction } from '@/helpers/api'

  interface Props {
    windows: WindowPrediction[]
    threshold: number
    selectedIndex: number | null
    onSelect: (index: number, seekAudio: boolean) => void
  }

  let { windows, threshold, selectedIndex, onSelect }: Props = $props()

  let thresholdBottomPct = $derived(
    Math.max(4, Math.min(96, threshold * 100))
  )

  let emergencyCount = $derived(
    windows.filter(w => w.label === 'EMERGENCY').length
  )
</script>

<div
  class="overflow-hidden rounded-xl border border-[var(--studio-border)] bg-[var(--studio-bg)]"
  aria-label="Perfil de scores sigmoide por ventana temporal"
>
  <div
    class="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--studio-border)] px-4 py-2.5"
  >
    <div class="flex items-center gap-2.5">
      <span class="caption-4 font-mono text-[var(--studio-text)]">
        PERFIL DE SCORES POR VENTANA
      </span>
      <span class="caption-4 font-mono text-[var(--studio-muted)] tabular-nums">
        {emergencyCount}/{windows.length} ≥ {threshold.toFixed(4)}
      </span>
    </div>
    <div class="flex items-center gap-3 font-mono text-[11px] text-[var(--studio-muted)]">
      <span class="inline-flex items-center gap-1.5">
        <span class="h-0.5 w-3.5 border-t border-dashed border-[#f0c779]" aria-hidden="true"></span>
        Umbral {threshold.toFixed(4)}
      </span>
      <span class="hidden sm:inline">Score sigmoide no calibrado (0–1)</span>
    </div>
  </div>

  <div class="relative px-4 pt-6 pb-4">
    <!-- Escala vertical izquierda + área de columnas -->
    <div class="grid grid-cols-[36px_minmax(0,1fr)] gap-3">
      <div
        class="flex h-[140px] flex-col justify-between text-right font-mono text-[10px] text-[var(--studio-muted)] tabular-nums"
        aria-hidden="true"
      >
        <span>1.00</span>
        <span>0.50</span>
        <span>0.00</span>
      </div>

      <div class="relative h-[140px]">
        <!-- Líneas de referencia horizontales -->
        <div
          class="pointer-events-none absolute inset-x-0 top-0 border-t border-[var(--studio-border)]/50"
          aria-hidden="true"
        ></div>
        <div
          class="pointer-events-none absolute inset-x-0 top-1/2 border-t border-[var(--studio-border)]/40"
          aria-hidden="true"
        ></div>
        <div
          class="pointer-events-none absolute inset-x-0 bottom-0 border-t border-[var(--studio-border)]"
          aria-hidden="true"
        ></div>

        <!-- Línea horizontal del umbral congelado (siempre visible sobre las columnas) -->
        <div
          class="pointer-events-none absolute inset-x-0 z-30 border-t-2 border-dashed border-[#f0c779]"
          style:bottom={`${thresholdBottomPct}%`}
          aria-hidden="true"
        >
          <span
            class="absolute -top-5 right-0 rounded border border-[#f0c779]/60 bg-[#090f1d] px-1.5 py-0.5 font-mono text-[10px] font-medium text-[#ffdf9f] tabular-nums shadow-sm"
          >
            θ {threshold.toFixed(4)}
          </span>
        </div>

        <!-- Columnas interactivas por ventana -->
        <div
          class="relative z-20 flex h-full items-end gap-2 overflow-x-auto pb-0.5"
          role="group"
          aria-label="Ventanas clasificadas"
        >
          {#each windows as win (win.index)}
            {@const isEmergency = win.label === 'EMERGENCY'}
            {@const isSelected = selectedIndex === win.index}
            {@const heightPct = Math.max(6, Math.min(100, win.score * 100))}
            <button
              type="button"
              aria-pressed={isSelected}
              aria-label={`Ventana ${win.index + 1}, de ${win.start_seconds.toFixed(1)} a ${win.end_seconds.toFixed(1)} segundos, score ${win.score.toFixed(4)}, ${win.label}`}
              title={`#${win.index + 1} (${win.start_seconds.toFixed(1)}–${win.end_seconds.toFixed(1)} s) · score ${win.score.toFixed(4)} · ${win.label}`}
              class="group relative flex h-full min-w-[26px] max-w-[84px] flex-1 cursor-pointer flex-col justify-end rounded-t-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-accent)]"
              onclick={() => onSelect(win.index, true)}
            >
              <span
                class={[
                  'relative flex w-full flex-col items-center justify-start overflow-hidden rounded-t-md border-x border-t transition-opacity duration-150',
                  isEmergency
                    ? isSelected
                      ? 'border-[#f0c779] bg-[#f0c779]/40 ring-2 ring-[#f5f3ec]'
                      : 'border-[#f0c779] bg-[#f0c779]/25'
                    : isSelected
                      ? 'border-[#5a78e6] bg-[#4969e3]/45 ring-2 ring-[#f5f3ec]'
                      : 'border-[#5a78e6] bg-[#4969e3]/25'
                ]}
                style:height={`${heightPct}%`}
              >
                <span
                  class="h-1 w-full shrink-0"
                  class:bg-[#f0c779]={isEmergency}
                  class:bg-[#9bb1ff]={!isEmergency}
                ></span>
                {#if windows.length <= 16}
                  <span
                    class="mt-1 font-mono text-[10px] font-medium tabular-nums"
                    class:text-[#ffdf9f]={isEmergency}
                    class:text-[var(--studio-text)]={!isEmergency}
                  >
                    {win.score.toFixed(2)}
                  </span>
                {/if}
              </span>
            </button>
          {/each}
        </div>
      </div>
    </div>

    <!-- Eje temporal inferior resumido -->
    <div
      class="mt-2.5 flex flex-wrap items-center justify-between gap-2 pl-[48px] font-mono text-[10px] text-[var(--studio-muted)] tabular-nums"
    >
      <span>V01 · {windows[0]?.start_seconds.toFixed(1)} s</span>
      {#if selectedIndex !== null && windows[selectedIndex]}
        <span class="text-[var(--studio-text)]">
          Seleccionada: #{selectedIndex + 1} ({windows[selectedIndex].start_seconds.toFixed(1)}–{windows[selectedIndex].end_seconds.toFixed(1)} s) · score {windows[selectedIndex].score.toFixed(4)}
        </span>
      {/if}
      <span>
        V{String(windows.length).padStart(2, '0')} · {windows[windows.length - 1]?.end_seconds.toFixed(1)} s
      </span>
    </div>
  </div>
</div>
