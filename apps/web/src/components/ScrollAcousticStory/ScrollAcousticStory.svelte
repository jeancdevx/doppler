<script lang="ts">
  import { onMount } from 'svelte'

  interface Chapter {
    id: string
    step: string
    title: string
    subtitle: string
    spec: string
  }

  const CHAPTERS: Chapter[] = [
    {
      id: 'capture',
      step: '01 / ARMONIZACIÓN',
      title: 'Mono 16 000 Hz y pico a 0,99.',
      subtitle:
        'Cada WAV se promedia a mono, se remuestrea con soxr_hq y se normaliza por pico del archivo completo para preservar la dinámica relativa sin reescalar por ventana.',
      spec: 'SR = 16 000 Hz · peak_target = 0.99'
    },
    {
      id: 'windowing',
      step: '02 / VENTANAS SOLAPADAS',
      title: 'Bloques exactos de 3,0 s cada 1,5 s.',
      subtitle:
        'El audio se corta en ventanas completas de 48 000 muestras con solapamiento del 50 %. Los archivos menores de 3,0 s y la cola incompleta nunca se rellenan silenciosamente.',
      spec: 'N = 48 000 · H = 24 000 · drop_incomplete_tail'
    },
    {
      id: 'logmel',
      step: '03 / PAISAJE LOG-MEL',
      title: '64 bandas Mel × 94 marcos temporales.',
      subtitle:
        'STFT con FFT 2048, salto 512 y ventana Hann periódica proyectada sobre banco Slaney (20 a 8 000 Hz) y rango dinámico de 80 dB respecto al máximo de cada segmento.',
      spec: 'Shape (64, 94) · Slaney · top_db = 80'
    },
    {
      id: 'resnet',
      step: '04 / DECISIÓN RESNET18',
      title: 'Inferencia CPU y umbral 0,6548.',
      subtitle:
        'Estandarización fija por banda, repetición a 3 canales en resolución nativa y salida sigmoide sin calibrar evaluada contra el umbral congelado de validación cruzada.',
      spec: 'VisualTransfer · Dropout 0.3 · σ(z) ≥ 0.6548'
    }
  ]

  let trackEl = $state<HTMLElement | undefined>(undefined)
  let canvasEl = $state<HTMLCanvasElement | undefined>(undefined)
  let activeIndex = $state(0)
  let scrollProgress = $state(0)
  let reducedMotion = $state(false)

  function lerp(a: number, b: number, t: number): number {
    return a + (b - a) * Math.max(0, Math.min(1, t))
  }

  function jumpToChapter(index: number) {
    if (!trackEl) {
      return
    }

    const rect = trackEl.getBoundingClientRect()
    const trackTop = window.scrollY + rect.top
    const scrollable = Math.max(1, trackEl.offsetHeight - window.innerHeight)
    const targetY = trackTop + (index / (CHAPTERS.length - 1)) * scrollable

    window.scrollTo({
      top: targetY,
      behavior: reducedMotion ? 'auto' : 'smooth'
    })
  }

  onMount(() => {
    reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    const canvas = canvasEl

    if (!canvas) {
      return
    }

    let width = 0
    let height = 0
    let targetProgress = 0
    let smoothProgress = 0
    let rafId = 0

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)

      width = Math.max(320, Math.floor(rect.width))
      height = Math.max(320, Math.floor(rect.height))
      canvas.width = Math.floor(width * dpr)
      canvas.height = Math.floor(height * dpr)

      const ctx = canvas.getContext('2d')

      if (ctx) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      }
    }

    const drawStage = (p: number) => {
      const ctx = canvas.getContext('2d')

      if (!ctx || width === 0 || height === 0) {
        return
      }

      ctx.clearRect(0, 0, width, height)

      // Pesos suaves de transición entre los 4 capítulos (scroll-scrub continuo sin cortes)
      const wWindow = Math.max(0, Math.min(1, (p - 0.16) / 0.22))
      const wMel = Math.max(0, Math.min(1, (p - 0.45) / 0.22))
      const wResnet = Math.max(0, Math.min(1, (p - 0.74) / 0.2))

      const padX = width * 0.08
      const drawW = width - padX * 2
      const centerY = height * 0.5

      // Retícula técnica sutil
      ctx.strokeStyle = 'rgba(155, 177, 255, 0.07)'
      ctx.lineWidth = 1

      for (let i = 0; i <= 12; i += 1) {
        const x = padX + (drawW / 12) * i

        ctx.beginPath()
        ctx.moveTo(x, height * 0.14)
        ctx.lineTo(x, height * 0.86)
        ctx.stroke()
      }

      // Fase 1 & 2: Onda acústica continua + raíles ±0.99 + ventanas solapadas 3,0 s
      const waveAlpha = Math.max(0, 1 - wMel * 1.15)

      if (waveAlpha > 0.01) {
        // Raíles de pico ±0.99
        ctx.strokeStyle = `rgba(155, 177, 255, ${0.24 * waveAlpha})`
        ctx.setLineDash([4, 6])
        ctx.beginPath()
        ctx.moveTo(padX, centerY - height * 0.22)
        ctx.lineTo(padX + drawW, centerY - height * 0.22)
        ctx.moveTo(padX, centerY + height * 0.22)
        ctx.lineTo(padX + drawW, centerY + height * 0.22)
        ctx.stroke()
        ctx.setLineDash([])

        // Ventanas solapadas (aparecen progresivamente en el capítulo 2)
        if (wWindow > 0.01) {
          const winSpecs = [
            { x0: 0.0, x1: 0.46, label: 'W0 · 0,0–3,0 s', active: false },
            { x0: 0.23, x1: 0.69, label: 'W1 · 1,5–4,5 s', active: true },
            { x0: 0.46, x1: 0.92, label: 'W2 · 3,0–6,0 s', active: true }
          ]

          for (let i = 0; i < winSpecs.length; i += 1) {
            const ws = winSpecs[i]
            const yOff = (i - 1) * 14 * wWindow
            const wx = padX + ws.x0 * drawW
            const ww = (ws.x1 - ws.x0) * drawW
            const wy = centerY - height * 0.25 + yOff
            const wh = height * 0.5

            ctx.fillStyle = ws.active
              ? `rgba(240, 199, 121, ${0.09 * wWindow * waveAlpha})`
              : `rgba(155, 177, 255, ${0.07 * wWindow * waveAlpha})`
            ctx.fillRect(wx, wy, ww, wh)

            ctx.strokeStyle = ws.active
              ? `rgba(240, 199, 121, ${0.75 * wWindow * waveAlpha})`
              : `rgba(155, 177, 255, ${0.55 * wWindow * waveAlpha})`
            ctx.lineWidth = 1.5
            ctx.strokeRect(wx, wy, ww, wh)

            ctx.fillStyle = ws.active
              ? `rgba(255, 223, 159, ${wWindow * waveAlpha})`
              : `rgba(189, 196, 209, ${wWindow * waveAlpha})`
            ctx.font = '11px "IBM Plex Mono", monospace'
            ctx.fillText(ws.label, wx + 10, wy + 18)
          }
        }

        // Trazo principal de la onda modulada
        ctx.beginPath()
        const pts = 220

        for (let i = 0; i <= pts; i += 1) {
          const u = i / pts
          const x = padX + u * drawW
          const sirenEnv = Math.exp(-Math.pow((u - 0.56) / 0.26, 2))
          const amp = (0.2 + 0.78 * sirenEnv) * (height * 0.21)
          const carrier = Math.sin(
            u * Math.PI * (18 + 10 * Math.sin(u * Math.PI * 2 + p * 6))
          )
          const y = centerY - carrier * amp

          if (i === 0) {
            ctx.moveTo(x, y)
          } else {
            ctx.lineTo(x, y)
          }
        }

        ctx.strokeStyle = `rgba(155, 177, 255, ${0.95 * waveAlpha})`
        ctx.lineWidth = 2.2
        ctx.stroke()
      }

      // Fase 3: Paisaje topográfico 3D Log-Mel 64 × 94
      const melAlpha = wMel * (1 - wResnet * 0.55)

      if (melAlpha > 0.01) {
        const bands = 22
        const colsMel = 72
        const scaleX = lerp(1, 0.56, wResnet)
        const offsetX = lerp(0, -drawW * 0.16, wResnet)

        for (let b = 0; b < bands; b += 1) {
          const d = b / (bands - 1)
          const rowY =
            height * 0.24 + d * (height * 0.56) + (1 - wMel) * 40
          const isHarmonic = b >= 7 && b <= 14

          ctx.beginPath()

          for (let c = 0; c <= colsMel; c += 1) {
            const u = c / colsMel
            const x = padX + offsetX + u * drawW * scaleX
            const ridgeCenter = 0.52 + 0.24 * Math.sin(u * Math.PI * 3.2 + p * 4)
            const ridge = Math.exp(-Math.pow((d - ridgeCenter) / 0.14, 2))
            const secondRidge =
              0.55 * Math.exp(-Math.pow((d - (ridgeCenter - 0.26)) / 0.1, 2))
            const elev = (ridge + secondRidge) * 34 * wMel

            const y = rowY - elev

            if (c === 0) {
              ctx.moveTo(x, y)
            } else {
              ctx.lineTo(x, y)
            }
          }

          ctx.strokeStyle = isHarmonic
            ? `rgba(240, 199, 121, ${(0.25 + d * 0.65) * melAlpha})`
            : `rgba(155, 177, 255, ${(0.18 + d * 0.55) * melAlpha})`
          ctx.lineWidth = isHarmonic ? 1.8 : 1.15
          ctx.stroke()
        }

        ctx.fillStyle = `rgba(155, 177, 255, ${0.9 * melAlpha})`
        ctx.font = '11px "IBM Plex Mono", monospace'
        ctx.fillText('64 BANDAS MEL (20–8000 HZ) × 94 MARCOS', padX, height * 0.18)
      }

      // Fase 4: Bloques ResNet18 + Plano de umbral 0.6548 + Salida EMERGENCY
      if (wResnet > 0.01) {
        const blocks = [
          { name: 'conv1', x: 0.52, h: 0.44 },
          { name: 'layer1–2', x: 0.61, h: 0.36 },
          { name: 'layer3–4', x: 0.70, h: 0.28 },
          { name: 'fc → σ(z)', x: 0.79, h: 0.18 }
        ]

        for (let i = 0; i < blocks.length; i += 1) {
          const blk = blocks[i]
          const bx = padX + blk.x * drawW
          const bw = drawW * 0.062
          const bh = height * blk.h
          const by = centerY - bh / 2

          ctx.fillStyle = `rgba(16, 27, 48, ${0.9 * wResnet})`
          ctx.fillRect(bx, by, bw, bh)
          ctx.strokeStyle =
            i === 3
              ? `rgba(240, 199, 121, ${0.95 * wResnet})`
              : `rgba(155, 177, 255, ${0.75 * wResnet})`
          ctx.lineWidth = 1.6
          ctx.strokeRect(bx, by, bw, bh)

          ctx.fillStyle = `rgba(245, 243, 236, ${wResnet})`
          ctx.font = '10px "IBM Plex Mono", monospace'
          ctx.fillText(blk.name, bx + 4, by - 8)
        }

        // Indicador visual del umbral 0.6548
        const gaugeX = padX + drawW * 0.89
        const gaugeW = drawW * 0.09
        const gaugeTop = height * 0.22
        const gaugeH = height * 0.56
        const threshY = gaugeTop + gaugeH * (1 - 0.6548)
        const scoreH = gaugeH * 0.86 * wResnet

        ctx.fillStyle = `rgba(16, 27, 48, ${0.9 * wResnet})`
        ctx.fillRect(gaugeX, gaugeTop, gaugeW, gaugeH)
        ctx.fillStyle = `rgba(240, 199, 121, ${0.88 * wResnet})`
        ctx.fillRect(gaugeX + 4, gaugeTop + gaugeH - scoreH, gaugeW - 8, scoreH)

        ctx.strokeStyle = `rgba(245, 243, 236, ${0.9 * wResnet})`
        ctx.setLineDash([4, 4])
        ctx.beginPath()
        ctx.moveTo(gaugeX - 10, threshY)
        ctx.lineTo(gaugeX + gaugeW + 10, threshY)
        ctx.stroke()
        ctx.setLineDash([])

        ctx.fillStyle = `rgba(255, 223, 159, ${wResnet})`
        ctx.font = '11px "IBM Plex Mono", monospace'
        ctx.fillText('0.6548', gaugeX - 4, threshY - 8)
        ctx.fillText('EMERGENCY', gaugeX - 8, gaugeTop - 10)
      }
    }

    const updateTargetFromScroll = () => {
      if (!trackEl) {
        return
      }

      const rect = trackEl.getBoundingClientRect()
      const scrollable = Math.max(1, trackEl.offsetHeight - window.innerHeight)
      const raw = Math.max(0, Math.min(1, -rect.top / scrollable))

      targetProgress = raw
      scrollProgress = raw
      activeIndex = Math.min(
        CHAPTERS.length - 1,
        Math.floor(raw * CHAPTERS.length * 0.999)
      )

      if (reducedMotion) {
        smoothProgress = targetProgress
        drawStage(smoothProgress)
      }
    }

    resize()
    updateTargetFromScroll()
    drawStage(smoothProgress)

    if (!reducedMotion) {
      const tick = () => {
        smoothProgress += (targetProgress - smoothProgress) * 0.14
        drawStage(smoothProgress)
        rafId = requestAnimationFrame(tick)
      }

      rafId = requestAnimationFrame(tick)
    }

    window.addEventListener('scroll', updateTargetFromScroll, { passive: true })
    window.addEventListener('resize', resize)

    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('scroll', updateTargetFromScroll)
      window.removeEventListener('resize', resize)
    }
  })
</script>

<section
  id="recorrido"
  bind:this={trackEl}
  class="relative bg-[#090f1d] text-[#f5f3ec] md:min-h-[280vh]"
  aria-label="Recorrido interactivo por el pipeline acústico de Doppler"
>
  <!-- Vista móvil y reduced-motion: tarjetas limpias sin bloqueo de scroll -->
  <div class="mx-auto flex max-w-[1440px] flex-col gap-5 px-5 py-14 md:hidden">
    <div>
      <span class="caption-4 font-mono text-[#9bb1ff]">
        RECORRIDO DEL PIPELINE
      </span>
      <h2 class="heading-3 mt-2 text-[#f5f3ec]">
        Cuatro etapas fieles a la notebook entrenada.
      </h2>
    </div>
    {#each CHAPTERS as chapter (chapter.id)}
      <article
        class="rounded-2xl border border-[#34435c] bg-[#101b30] p-5"
      >
        <span class="caption-4 font-mono text-[#9bb1ff]">{chapter.step}</span>
        <h3 class="heading-4 mt-2 text-[#f5f3ec]">{chapter.title}</h3>
        <p class="body-6 mt-2 text-[#bdc4d1]">{chapter.subtitle}</p>
        <p class="mt-3 font-mono text-[11px] text-[#ffdf9f]">{chapter.spec}</p>
      </article>
    {/each}
  </div>

  <!-- Escenario cinematográfico sticky en escritorio (scroll-scrub continuo) -->
  <div class="sticky top-0 hidden h-[100dvh] flex-col overflow-hidden md:flex">
    <div class="mx-auto flex min-h-0 w-full max-w-[1440px] flex-1 flex-col gap-5 px-8 pt-24 pb-8">
      <div class="flex shrink-0 items-start justify-between gap-8">
        <div class="max-w-[540px]">
          <span class="caption-4 font-mono text-[#9bb1ff]">
            {CHAPTERS[activeIndex].step}
          </span>
          <h2 class="heading-2 mt-2 text-[#f5f3ec]">
            {CHAPTERS[activeIndex].title}
          </h2>
          <p class="body-3 mt-3 text-[#bdc4d1]">
            {CHAPTERS[activeIndex].subtitle}
          </p>
          <p
            class="mt-4 inline-flex items-center gap-2 rounded-lg border border-[#34435c] bg-[#101b30] px-3 py-1.5 font-mono text-xs text-[#ffdf9f]"
          >
            {CHAPTERS[activeIndex].spec}
          </p>
        </div>

        <!-- Rail lateral interactivo de capítulos -->
        <nav
          class="flex flex-col gap-2"
          aria-label="Capítulos del pipeline acústico"
        >
          {#each CHAPTERS as ch, idx (ch.id)}
            <button
              type="button"
              class="flex cursor-pointer items-center justify-end gap-3 rounded-lg px-3 py-1.5 text-right font-mono text-xs transition-colors"
              class:text-[#f5f3ec]={activeIndex === idx}
              class:bg-[#101b30]={activeIndex === idx}
              class:text-[#949fb3]={activeIndex !== idx}
              aria-current={activeIndex === idx ? 'step' : undefined}
              onclick={() => jumpToChapter(idx)}
            >
              <span>{ch.step}</span>
              <span
                class="h-1.5 rounded-full transition-all"
                class:w-7={activeIndex === idx}
                class:bg-[#f0c779]={activeIndex === idx}
                class:w-2.5={activeIndex !== idx}
                class:bg-[#34435c]={activeIndex !== idx}
              ></span>
            </button>
          {/each}
        </nav>
      </div>

      <!-- Lienzo continuo de transformación señal -> ventanas -> Log-Mel -> ResNet18 -->
      <div
        class="relative min-h-0 flex-1 overflow-hidden rounded-2xl border border-[#34435c] bg-[#0c1426]"
      >
        <canvas
          bind:this={canvasEl}
          class="block h-full w-full"
          aria-hidden="true"
        ></canvas>
        <div
          class="pointer-events-none absolute right-4 bottom-3 font-mono text-[11px] text-[#949fb3] tabular-nums"
        >
          PROGRESO DE SECUENCIA · {Math.round(scrollProgress * 100)} %
        </div>
      </div>
    </div>
  </div>
</section>
