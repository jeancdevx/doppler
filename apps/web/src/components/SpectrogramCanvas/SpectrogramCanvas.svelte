<script lang="ts">
  import type { WindowPrediction } from '@/helpers/api'
  import { formatClock } from '@/helpers/format'
  import type { ComputedSpectrogram } from '@/helpers/wav'

  interface Props {
    spectrogram: ComputedSpectrogram | null
    currentTime: number
    windows: WindowPrediction[]
    selectedIndex: number | null
    onSeek: (seconds: number) => void
  }

  let { spectrogram, currentTime, windows, selectedIndex, onSeek }: Props = $props()

  let canvasEl: HTMLCanvasElement | undefined = $state()

  function colorForMagnitude(norm: number): [number, number, number] {
    // Rampa perceptual Espectro: #090F1D -> #233B88 -> #5275EF -> #9BB1FF -> #FFDF9F
    const v = Math.max(0, Math.min(1, norm))

    if (v < 0.35) {
      const t = v / 0.35

      return [
        Math.round(9 + t * (35 - 9)),
        Math.round(15 + t * (59 - 15)),
        Math.round(29 + t * (136 - 29))
      ]
    }

    if (v < 0.7) {
      const t = (v - 0.35) / 0.35

      return [
        Math.round(35 + t * (82 - 35)),
        Math.round(59 + t * (117 - 59)),
        Math.round(136 + t * (239 - 136))
      ]
    }

    const t = (v - 0.7) / 0.3

    return [
      Math.round(82 + t * (255 - 82)),
      Math.round(117 + t * (223 - 117)),
      Math.round(239 + t * (159 - 239))
    ]
  }

  $effect(() => {
    const canvas = canvasEl

    if (!canvas || !spectrogram) {
      return
    }

    const width = Math.max(320, Math.floor(canvas.clientWidth || 720))
    const height = 176

    canvas.width = width
    canvas.height = height

    const ctx = canvas.getContext('2d')

    if (!ctx) {
      return
    }

    const img = ctx.createImageData(width, height)
    const { frames, bins, magnitudes, durationSeconds } = spectrogram

    for (let x = 0; x < width; x += 1) {
      const frameIdx = Math.min(frames - 1, Math.floor((x / width) * frames))

      for (let y = 0; y < height; y += 1) {
        const binIdx = Math.min(
          bins - 1,
          Math.floor(((height - 1 - y) / height) * bins)
        )
        const val = magnitudes[frameIdx * bins + binIdx]
        const [r, g, b] = colorForMagnitude(val)
        const p = (y * width + x) * 4

        img.data[p] = r
        img.data[p + 1] = g
        img.data[p + 2] = b
        img.data[p + 3] = 255
      }
    }

    ctx.putImageData(img, 0, 0)

    if (durationSeconds > 0) {
      const selected =
        selectedIndex !== null ? windows[selectedIndex] ?? null : null

      if (selected) {
        const x0 = (selected.start_seconds / durationSeconds) * width
        const w =
          ((selected.end_seconds - selected.start_seconds) / durationSeconds) * width

        ctx.strokeStyle =
          selected.label === 'EMERGENCY' ? '#f0c779' : '#9bb1ff'
        ctx.lineWidth = 2
        ctx.strokeRect(x0 + 1, 1, Math.max(2, w - 2), height - 2)
      }

      const playX = Math.max(
        1,
        Math.min(width - 1, (currentTime / durationSeconds) * width)
      )

      ctx.strokeStyle = '#f5f3ec'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(playX, 0)
      ctx.lineTo(playX, height)
      ctx.stroke()
    }
  })

  function handleClick(event: MouseEvent) {
    if (!canvasEl || !spectrogram || spectrogram.durationSeconds <= 0) {
      return
    }

    const rect = canvasEl.getBoundingClientRect()
    const frac = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))

    onSeek(frac * spectrogram.durationSeconds)
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (!spectrogram || spectrogram.durationSeconds <= 0) {
      return
    }

    if (event.key === 'ArrowRight') {
      event.preventDefault()
      onSeek(Math.min(spectrogram.durationSeconds, currentTime + 1.5))
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      onSeek(Math.max(0, currentTime - 1.5))
    }
  }
</script>

{#if spectrogram}
  <div class="flex flex-col gap-2">
    <div
      class="relative cursor-pointer overflow-hidden rounded-lg border border-[var(--studio-border)]"
      role="slider"
      tabindex="0"
      aria-label={`Espectrograma Log-Mel calculado desde el audio cargado (${spectrogram.bins} bandas, 20 Hz a ${Math.round(spectrogram.maxFrequencyHz)} Hz, FFT ${spectrogram.fftSize})`}
      aria-valuemin={0}
      aria-valuemax={Math.round(spectrogram.durationSeconds * 10) / 10}
      aria-valuenow={Math.round(currentTime * 10) / 10}
      onclick={handleClick}
      onkeydown={handleKeyDown}
    >
      <canvas
        bind:this={canvasEl}
        class="block h-[176px] w-full"
        aria-hidden="true"
      ></canvas>
      <div
        class="pointer-events-none absolute top-2 left-2 rounded-md bg-[#090f1d]/80 px-2 py-0.5 font-mono text-[10px] text-[#f5f3ec]"
      >
        {Math.round(spectrogram.maxFrequencyHz)} Hz
      </div>
      <div
        class="pointer-events-none absolute bottom-2 left-2 rounded-md bg-[#090f1d]/80 px-2 py-0.5 font-mono text-[10px] text-[#f5f3ec]"
      >
        20 Hz
      </div>
      <div
        class="pointer-events-none absolute top-2 right-2 rounded-md bg-[#090f1d]/80 px-2 py-0.5 font-mono text-[10px] text-[#bdc4d1]"
      >
        STFT calculado del WAV · FFT {spectrogram.fftSize} · 64 bandas Mel · 80 dB
      </div>
    </div>
    <div
      class="flex justify-between px-1 font-mono text-[11px] text-[var(--studio-muted)] tabular-nums"
      aria-hidden="true"
    >
      <span>00:00.0</span>
      <span>{formatClock(spectrogram.durationSeconds * 0.5)}</span>
      <span>{formatClock(spectrogram.durationSeconds)}</span>
    </div>
  </div>
{:else}
  <div
    class="flex h-[176px] items-center justify-center rounded-lg border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 text-center text-sm text-[var(--studio-muted)]"
  >
    Carga o reproduce un audio WAV para calcular su espectrograma real desde la señal.
  </div>
{/if}
