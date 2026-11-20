<script lang="ts">
  import { onMount } from 'svelte'

  let canvasEl = $state<HTMLCanvasElement | undefined>(undefined)
  let hoveredFreqHz = $state<number>(1140)
  let hoveredTimeSec = $state<number>(3.8)

  onMount(() => {
    const canvas = canvasEl

    if (!canvas) {
      return
    }

    const reducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)'
    ).matches
    const finePointer = window.matchMedia(
      '(hover: hover) and (pointer: fine)'
    ).matches

    let width = 0
    let height = 0
    let rafId = 0
    let phase = 0

    // Estado objetivo y suavizado (amortiguado) para eliminar saltos al cruzar cajas/tarjetas
    let pointerInsideHero = false
    let targetX = 0.64
    let targetY = 0.48
    let smoothX = 0.64
    let smoothY = 0.48
    let lastHudUpdate = 0

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)

      width = Math.max(320, Math.floor(rect.width))
      height = Math.max(360, Math.floor(rect.height))
      canvas.width = Math.floor(width * dpr)
      canvas.height = Math.floor(height * dpr)

      const ctx = canvas.getContext('2d')

      if (ctx) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      }
    }

    // Función determinista para evaluar la altura exacta de una cinta en u ∈ [0, 1]
    const evaluateRibbonY = (
      u: number,
      r: number,
      ribbons: number,
      t: number,
      horizonY: number,
      focalX: number,
      tiltOffset: number
    ) => {
      const depth = r / (ribbons - 1)
      const baseY = horizonY - 110 + depth * 225 + tiltOffset * (depth - 0.5)
      const x = u * width
      const distFromFocus = (x - focalX) / (width * 0.25)
      const envelope = Math.exp(-distFromFocus * distFromFocus)

      const freqSweep = 5.5 + 3.0 * Math.sin(t * 0.65 + depth * 2.1)
      const primary =
        Math.sin(u * Math.PI * freqSweep - t * 1.35 + depth * 4.1) *
        (20 + depth * 60) *
        envelope
      const harmonic =
        Math.sin(u * Math.PI * 12.5 + t * 1.9 - depth * 5.8) *
        (7 + depth * 16) *
        envelope
      const ambient =
        Math.sin(u * Math.PI * 3.0 + t * 0.45 + r * 0.4) * (3.5 + depth * 5.5)

      return baseY - (primary + harmonic + ambient)
    }

    const drawFrame = (t: number) => {
      const ctx = canvas.getContext('2d')

      if (!ctx || width === 0 || height === 0) {
        return
      }

      // Si el puntero está fuera de la portada, regresa suavemente al barrido autónomo sin saltos
      const desiredX = pointerInsideHero
        ? targetX
        : 0.66 + Math.sin(t * 0.35) * 0.08
      const desiredY = pointerInsideHero ? targetY : 0.48
      const damping = pointerInsideHero ? 0.085 : 0.04

      smoothX += (desiredX - smoothX) * damping
      smoothY += (desiredY - smoothY) * damping

      // Actualiza telemetría HUD a ritmo cómodo (~15 Hz) sin forzar re-render excesivo
      if (t - lastHudUpdate > 0.06) {
        lastHudUpdate = t
        hoveredFreqHz = Math.round(20 + (1 - smoothY) * 7980)
        hoveredTimeSec = Math.round(smoothX * 60) / 10
      }

      ctx.clearRect(0, 0, width, height)

      // 1. Retícula acústica calibrada
      const horizonY = height * 0.56
      const cols = 14

      ctx.strokeStyle = 'rgba(155, 177, 255, 0.055)'
      ctx.lineWidth = 1

      for (let i = 0; i <= cols; i += 1) {
        const x = (width / cols) * i

        ctx.beginPath()
        ctx.moveTo(x, 0)
        ctx.lineTo(x, height)
        ctx.stroke()
      }

      for (let row = 0; row <= 8; row += 1) {
        const y = (height / 8) * row

        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(width, y)
        ctx.stroke()
      }

      // 2. Campo de 26 cintas espectrales 3D con barrido armónico Doppler
      const ribbons = 26
      const samples = 100
      const focalX = width * (0.58 + (smoothX - 0.5) * 0.24)
      const tiltOffset = (smoothY - 0.5) * 24

      for (let r = 0; r < ribbons; r += 1) {
        const depth = r / (ribbons - 1)
        const isSirenBand = r >= 12 && r <= 18
        const alpha = 0.07 + depth * (isSirenBand ? 0.56 : 0.3)

        ctx.beginPath()

        for (let s = 0; s <= samples; s += 1) {
          const u = s / samples
          const x = u * width
          const y = evaluateRibbonY(
            u,
            r,
            ribbons,
            t,
            horizonY,
            focalX,
            tiltOffset
          )

          if (s === 0) {
            ctx.moveTo(x, y)
          } else {
            ctx.lineTo(x, y)
          }
        }

        if (r === 15) {
          ctx.strokeStyle = `rgba(240, 199, 121, ${alpha + 0.22})`
          ctx.lineWidth = 2.2
        } else if (isSirenBand) {
          ctx.strokeStyle = `rgba(155, 177, 255, ${alpha})`
          ctx.lineWidth = 1.35
        } else {
          ctx.strokeStyle = `rgba(49, 86, 211, ${alpha})`
          ctx.lineWidth = 1
        }

        ctx.stroke()
      }

      // 3. Línea de escaneo acústico amortiguada + retícula clavada exactamente sobre la cinta dominante r=15
      const scanX = smoothX * width
      const nodeY = evaluateRibbonY(
        smoothX,
        15,
        ribbons,
        t,
        horizonY,
        focalX,
        tiltOffset
      )

      const scanGrad = ctx.createLinearGradient(0, 40, 0, height - 40)

      scanGrad.addColorStop(0, 'rgba(245, 243, 236, 0)')
      scanGrad.addColorStop(0.2, 'rgba(245, 243, 236, 0.32)')
      scanGrad.addColorStop(0.8, 'rgba(245, 243, 236, 0.32)')
      scanGrad.addColorStop(1, 'rgba(245, 243, 236, 0)')

      ctx.strokeStyle = scanGrad
      ctx.lineWidth = 1
      ctx.setLineDash([4, 6])
      ctx.beginPath()
      ctx.moveTo(scanX, 40)
      ctx.lineTo(scanX, height - 40)
      ctx.stroke()
      ctx.setLineDash([])

      // Halo suave + punto central sobre la señal
      const halo = ctx.createRadialGradient(
        scanX,
        nodeY,
        2,
        scanX,
        nodeY,
        22
      )

      halo.addColorStop(0, 'rgba(240, 199, 121, 0.45)')
      halo.addColorStop(1, 'rgba(240, 199, 121, 0)')
      ctx.fillStyle = halo
      ctx.beginPath()
      ctx.arc(scanX, nodeY, 22, 0, Math.PI * 2)
      ctx.fill()

      ctx.fillStyle = '#f0c779'
      ctx.beginPath()
      ctx.arc(scanX, nodeY, 4.5, 0, Math.PI * 2)
      ctx.fill()

      ctx.strokeStyle = 'rgba(240, 199, 121, 0.65)'
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(scanX, nodeY, 10.5, 0, Math.PI * 2)
      ctx.stroke()
    }

    resize()
    drawFrame(0.8)

    if (!reducedMotion) {
      const loop = () => {
        phase += 0.016
        drawFrame(phase)
        rafId = requestAnimationFrame(loop)
      }

      rafId = requestAnimationFrame(loop)
    }

    // Escucha global en window para que las tarjetas/textos encima del canvas jamás interrumpan el seguimiento
    const onWindowPointerMove = (event: PointerEvent) => {
      if (!finePointer) {
        return
      }

      const rect = canvas.getBoundingClientRect()
      const inside =
        event.clientX >= rect.left &&
        event.clientX <= rect.right &&
        event.clientY >= rect.top &&
        event.clientY <= rect.bottom

      pointerInsideHero = inside

      if (inside && rect.width > 0 && rect.height > 0) {
        targetX = Math.max(
          0.04,
          Math.min(0.96, (event.clientX - rect.left) / rect.width)
        )
        targetY = Math.max(
          0.06,
          Math.min(0.94, (event.clientY - rect.top) / rect.height)
        )
      }
    }

    const onWindowPointerOut = (event: MouseEvent) => {
      if (!event.relatedTarget) {
        pointerInsideHero = false
      }
    }

    window.addEventListener('resize', resize)
    window.addEventListener('pointermove', onWindowPointerMove, {
      passive: true
    })
    window.addEventListener('mouseout', onWindowPointerOut)

    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('resize', resize)
      window.removeEventListener('pointermove', onWindowPointerMove)
      window.removeEventListener('mouseout', onWindowPointerOut)
    }
  })
</script>

<div
  class="pointer-events-none absolute inset-0 overflow-hidden"
  aria-hidden="true"
>
  <canvas bind:this={canvasEl} class="block h-full w-full"></canvas>

  <!-- Escudo radial obsidiana detrás de la columna editorial izquierda para garantizar contraste nítido sin tapar las ondas -->
  <div
    class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_62%_78%_at_22%_46%,rgba(9,15,29,0.92)_0%,rgba(9,15,29,0.72)_46%,rgba(9,15,29,0.12)_80%,transparent_100%)]"
  ></div>

  <!-- Desvanecimiento suave en el borde inferior -->
  <div
    class="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-[#090f1d] to-transparent"
  ></div>

  <div
    class="pointer-events-none absolute top-24 right-6 hidden rounded-xl border border-[#34435c]/80 bg-[#090f1d]/85 px-3.5 py-1.5 font-mono text-[11px] text-[#bdc4d1] backdrop-blur-md lg:flex lg:items-center lg:gap-3"
  >
    <span class="text-[#f0c779]">SCAN</span>
    <span class="tabular-nums">{hoveredFreqHz} Hz</span>
    <span class="text-[#34435c]">|</span>
    <span class="tabular-nums">t = {hoveredTimeSec.toFixed(1)} s</span>
  </div>
</div>
