<script lang="ts">
  import CloudArrowUp from 'phosphor-svelte/lib/CloudArrowUp'
  import FileAudio from 'phosphor-svelte/lib/FileAudio'
  import ShieldCheck from 'phosphor-svelte/lib/ShieldCheck'
  import X from 'phosphor-svelte/lib/X'

  import { Button } from '@/components/ui/button'
  import { Progress } from '@/components/ui/progress'
  import type { LimitsInfo, UploadProgressInfo } from '@/helpers/api'
  import { formatBytes, middleTruncate } from '@/helpers/format'

  interface Props {
    limits: LimitsInfo
    busy: boolean
    uploading: boolean
    activeFilename: string | null
    uploadProgress: UploadProgressInfo | null
    onSelectFile: (file: File) => void
    onCancelUpload: () => void
  }

  let {
    limits,
    busy,
    uploading,
    activeFilename,
    uploadProgress,
    onSelectFile,
    onCancelUpload
  }: Props = $props()

  let dragging = $state(false)
  let fileInputEl: HTMLInputElement | undefined = $state()

  function handleDrop(event: DragEvent) {
    event.preventDefault()
    dragging = false

    if (busy) {
      return
    }

    const file = event.dataTransfer?.files?.[0]

    if (file) {
      onSelectFile(file)
    }
  }

  function handleFileChange(event: Event) {
    const input = event.currentTarget as HTMLInputElement
    const file = input.files?.[0]

    if (file) {
      onSelectFile(file)
    }

    input.value = ''
  }

  function openPicker() {
    if (!busy) {
      fileInputEl?.click()
    }
  }
</script>

<div
  class={[
    'relative overflow-hidden rounded-2xl border p-6 transition-colors sm:p-10',
    dragging
      ? 'border-[var(--studio-accent)] bg-[var(--studio-raised)]'
      : 'border-[var(--studio-border)] bg-[var(--studio-panel)]'
  ]}
  role="region"
  aria-label="Zona de carga de archivos WAV"
  ondragover={event => {
    event.preventDefault()
    if (!busy) {
      dragging = true
    }
  }}
  ondragleave={() => {
    dragging = false
  }}
  ondrop={handleDrop}
>
  <!-- Esquinas de calibración estilo instrumento acústico -->
  <span
    class="pointer-events-none absolute top-3 left-3 size-3.5 border-t-2 border-l-2 border-[var(--studio-accent)]/60"
    aria-hidden="true"
  ></span>
  <span
    class="pointer-events-none absolute top-3 right-3 size-3.5 border-t-2 border-r-2 border-[var(--studio-accent)]/60"
    aria-hidden="true"
  ></span>
  <span
    class="pointer-events-none absolute bottom-3 left-3 size-3.5 border-b-2 border-l-2 border-[var(--studio-accent)]/60"
    aria-hidden="true"
  ></span>
  <span
    class="pointer-events-none absolute right-3 bottom-3 size-3.5 border-r-2 border-b-2 border-[var(--studio-accent)]/60"
    aria-hidden="true"
  ></span>

  <input
    bind:this={fileInputEl}
    id="doppler-wav-input"
    type="file"
    accept=".wav,audio/wav,audio/x-wav,audio/wave"
    class="sr-only"
    onchange={handleFileChange}
    disabled={busy}
  />

  {#if uploading && uploadProgress}
    <div class="relative z-10 flex flex-col gap-5">
      <div class="flex items-start justify-between gap-4">
        <div class="flex min-w-0 items-center gap-3.5">
          <div
            class="flex size-11 shrink-0 items-center justify-center rounded-xl border border-[var(--studio-accent)]/50 bg-[var(--studio-bg)] text-[var(--studio-accent)]"
          >
            <FileAudio class="size-5" aria-hidden="true" />
          </div>
          <div class="min-w-0">
            <span class="caption-4 block font-mono text-[var(--studio-accent)]">
              TRANSFERENCIA DIRECTA PUT → CLOUDFLARE R2
            </span>
            <p
              class="title-3 mt-0.5 truncate text-[var(--studio-text)]"
              title={activeFilename ?? ''}
            >
              {middleTruncate(activeFilename ?? 'audio.wav', 42)}
            </p>
            <p class="mt-0.5 font-mono text-xs text-[var(--studio-muted)] tabular-nums">
              {formatBytes(uploadProgress.loaded)} / {formatBytes(uploadProgress.total)}
              · {formatBytes(uploadProgress.bytesPerSecond)}/s
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Cancelar carga"
          onclick={onCancelUpload}
        >
          <X class="size-4" aria-hidden="true" />
        </Button>
      </div>

      <div class="flex items-center gap-3">
        <Progress
          value={uploadProgress.percent}
          max={100}
          label="Progreso de carga hacia Cloudflare R2"
        />
        <span class="caption-4 shrink-0 font-mono text-[var(--studio-text)] tabular-nums">
          {uploadProgress.percent} %
        </span>
      </div>
    </div>
  {:else}
    <div class="relative z-10 flex flex-col items-center text-center">
      <div
        class="mb-4 flex size-14 items-center justify-center rounded-2xl border border-[var(--studio-accent)]/40 bg-[var(--studio-bg)] text-[var(--studio-accent)] shadow-inner"
      >
        <CloudArrowUp class="size-7" aria-hidden="true" />
      </div>

      <span class="caption-4 font-mono text-[var(--studio-accent)]">
        ENTRADA DE SEÑAL WAV · CLOUDFLARE R2 PRIVADO
      </span>

      <h4 class="heading-4 mt-2 text-[var(--studio-text)]">
        Arrastra un archivo WAV o selecciónalo desde tu equipo
      </h4>

      <p class="body-6 mt-2 max-w-[540px] text-[var(--studio-muted)]">
        Prevalidación instantánea de cabecera RIFF en tu navegador, subida directa
        firmada a R2 y análisis por ventanas completas de 3,0 s con salto de 1,5 s.
      </p>

      <!-- Tira de especificaciones técnicas en cápsulas -->
      <div
        class="mt-5 flex flex-wrap items-center justify-center gap-2 font-mono text-[11px] text-[var(--studio-muted)]"
      >
        <span class="rounded-md border border-[var(--studio-border)] bg-[var(--studio-bg)] px-2.5 py-1 text-[var(--studio-text)]">
          .WAV PCM
        </span>
        <span class="rounded-md border border-[var(--studio-border)] bg-[var(--studio-bg)] px-2.5 py-1 tabular-nums">
          Máx. {Math.round(limits.max_file_bytes / (1024 * 1024))} MiB
        </span>
        <span class="rounded-md border border-[var(--studio-border)] bg-[var(--studio-bg)] px-2.5 py-1 tabular-nums">
          3,0 s – {limits.max_duration_seconds} s
        </span>
        <span class="rounded-md border border-[var(--studio-border)] bg-[var(--studio-bg)] px-2.5 py-1">
          Sin relleno &lt; 3,0 s
        </span>
      </div>

      <div class="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Button variant="primary" size="lg" disabled={busy} onclick={openPicker}>
          <CloudArrowUp class="size-5" aria-hidden="true" />
          <span>{busy ? 'Procesando archivo…' : 'Seleccionar archivo WAV'}</span>
        </Button>
      </div>

      <div
        class="mt-6 flex items-center gap-2.5 rounded-xl border border-[var(--studio-border)] bg-[var(--studio-bg)] px-4 py-2.5 text-left text-xs text-[var(--studio-muted)]"
      >
        <ShieldCheck
          class="size-4 shrink-0 text-[var(--studio-accent)]"
          aria-hidden="true"
        />
        <span>
          Retención privada de <strong class="font-medium text-[var(--studio-text)]">{limits.retention_hours} horas</strong>
          en Cloudflare R2 bajo prefijo exclusivo de Doppler. Puedes eliminar tu audio y sus resultados en cualquier momento.
        </span>
      </div>
    </div>
  {/if}
</div>
