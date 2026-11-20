<script lang="ts">
  import type { WindowPrediction } from '@/helpers/api'
  import { formatClock } from '@/helpers/format'

  interface Props {
    peaks: Float32Array | null
    duration: number
    currentTime: number
    windows: WindowPrediction[]
    selectedIndex: number | null
    theme: 'dark' | 'light'
    onSeek: (seconds: number) => void
  }

  let {
    peaks,
    duration,
    currentTime,
    windows,
    selectedIndex,
    theme,
    onSeek
  }: Props = $props()

  let canvasEl: HTMLCanvasElement | undefined = $state()

  let timeTicks = $derived.by(() => {
    if (!duration || duration <= 0) {
      return ['00:00.0', '00:01.5', '00:03.0']
    }

    return [0, 0.25, 0.5, 0.75, 1].map(frac => formatClock(frac * duration))
  })

  $effect(() => {
    const canvas = canvasEl

    if (!canvas) {
      return
    }

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const width = Math.max(320, Math.floor(canvas.clientWidth || 720))
    const height = 176

    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr
      canvas.height = height * dpr
    }

    const ctx = canvas.getContext('2d')

    if (!ctx) {
      return
    }

    ctx.save()
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, width, height)

    const isDark = theme === 'dark'
    const gridColor = isDark ? 'rgba(52, 67, 92, 0.35)' : 'rgba(215, 217, 223, 0.75)'
    const waveColor = isDark ? '#9bb1ff' : '#3156d3'
    const waveTargetColor = isDark ? '#ffdf9f' : '#9c6300'
    const playheadColor = isDark ? '#f5f3ec' : '#172b4d'

    // Retícula técnica
    ctx.strokeStyle = gridColor
    ctx.lineWidth = 1

    for (let row = 1; row < 6; row += 1) {
      const y = Math.round((height / 6) * row) + 0.5

      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(width, y)
      ctx.stroke()
    }

    for (let col = 1; col < 12; col += 1) {
      const x = Math.round((width / 12) * col) + 0.5

      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, height)
      ctx.stroke()
    }

    // Sombreado de ventanas positivas EMERGENCY
    if (duration > 0) {
      for (const win of windows) {
        if (win.label !== 'EMERGENCY') {
          continue
        }

        const x0 = (win.start_seconds / duration) * width
        const w = ((win.end_seconds - win.start_seconds) / duration) * width

        ctx.fillStyle = isDark
          ? 'rgba(240, 199, 121, 0.14)'
          : 'rgba(216, 168, 78, 0.20)'
        ctx.fillRect(x0, 0, w, height)
      }

      // Marco de ventana seleccionada
      const selected =
        selectedIndex !== null ? windows[selectedIndex] ?? null : null

      if (selected) {
        const x0 = (selected.start_seconds / duration) * width
        const w = ((selected.end_seconds - selected.start_seconds) / duration) * width
        const stroke =
          selected.label === 'EMERGENCY'
            ? '#f0c779'
            : isDark
              ? '#9bb1ff'
              : '#3156d3'

        ctx.fillStyle =
          selected.label === 'EMERGENCY'
            ? isDark
              ? 'rgba(240, 199, 121, 0.22)'
              : 'rgba(216, 168, 78, 0.26)'
            : isDark
              ? 'rgba(155, 177, 255, 0.14)'
              : 'rgba(49, 86, 211, 0.12)'
        ctx.fillRect(x0, 0, w, height)

        ctx.strokeStyle = stroke
        ctx.lineWidth = 2
        ctx.strokeRect(x0 + 1, 1, Math.max(2, w - 2), height - 2)
      }
    }

    // Barras de forma de onda real
    const midY = height / 2

    if (peaks && peaks.length > 0) {
      const count = peaks.length
      const step = width / count
      const barWidth = Math.max(1.5, Math.min(3, step * 0.62))

      for (let i = 0; i < count; i += 1) {
        const x = i * step + step / 2
        const t = duration > 0 ? ((i + 0.5) / count) * duration : 0
        const inEmergency = windows.some(
          w => w.label === 'EMERGENCY' && t >= w.start_seconds && t <= w.end_seconds
        )
        const amp = Math.max(0.02, peaks[i])
        const barH = Math.max(3, amp * (height - 24))

        ctx.strokeStyle = inEmergency ? waveTargetColor : waveColor
        ctx.lineWidth = barWidth
        ctx.lineCap = 'round'
        ctx.beginPath()
        ctx.moveTo(x, midY - barH / 2)
        ctx.lineTo(x, midY + barH / 2)
        ctx.stroke()
      }
    } else {
      ctx.strokeStyle = gridColor
      ctx.beginPath()
      ctx.moveTo(0, midY)
      ctx.lineTo(width, midY)
      ctx.stroke()
    }

    // Cursor de reproducción
    if (duration > 0) {
      const playX = Math.max(1, Math.min(width - 1, (currentTime / duration) * width))

      ctx.strokeStyle = playheadColor
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(playX, 0)
      ctx.lineTo(playX, height)
      ctx.stroke()

      ctx.fillStyle = playheadColor
      ctx.beginPath()
      ctx.arc(playX, 8, 4, 0, Math.PI * 2)
      ctx.fill()
    }

    ctx.restore()
  })

  function seekFromPointer(event: MouseEvent) {
    if (!canvasEl || duration <= 0) {
      return
    }

    const rect = canvasEl.getBoundingClientRect()
    const frac = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))

    onSeek(frac * duration)
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (duration <= 0) {
      return
    }

    if (event.key === 'ArrowRight') {
      event.preventDefault()
      onSeek(Math.min(duration, currentTime + 1.5))
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      onSeek(Math.max(0, currentTime - 1.5))
    } else if (event.key === 'Home') {
      event.preventDefault()
      onSeek(0)
    } else if (event.key === 'End') {
      event.preventDefault()
      onSeek(duration)
    }
  }
</script>

<div class="flex flex-col gap-2">
  <div
    class="relative w-full cursor-pointer overflow-hidden rounded-lg"
    role="slider"
    tabindex="0"
    aria-label="Línea de tiempo de la forma de onda. Usa flechas izquierda y derecha para desplazarte."
    aria-valuemin={0}
    aria-valuemax={Math.round(duration * 10) / 10}
    aria-valuenow={Math.round(currentTime * 10) / 10}
    aria-valuetext={`${formatClock(currentTime)} de ${formatClock(duration)}`}
    onclick={seekFromPointer}
    onkeydown={handleKeyDown}
  >
    <canvas
      bind:this={canvasEl}
      class="block h-[176px] w-full"
      aria-hidden="true"
    ></canvas>
  </div>

  <div
    class="flex justify-between px-1 font-mono text-[11px] text-[var(--studio-muted)] tabular-nums"
    aria-hidden="true"
  >
    {#each timeTicks as tick, idx (idx)}
      <span>{tick}</span>
    {/each}
  </div>
</div>
