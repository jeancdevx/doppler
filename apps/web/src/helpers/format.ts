const spanishNumber = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1
})

const spanishScore = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4
})

export function formatClock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return '00:00.0'
  }

  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  const tenths = Math.floor((seconds - Math.floor(seconds)) * 10)

  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${tenths}`
}

export function formatSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return '—'
  }

  return `${spanishNumber.format(seconds)} s`
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined || !Number.isFinite(score)) {
    return '—'
  }

  return spanishScore.format(score)
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) {
    return '—'
  }

  if (bytes < 1024) {
    return `${bytes} B`
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1).replace('.', ',')} KiB`
  }

  return `${(bytes / (1024 * 1024)).toFixed(2).replace('.', ',')} MiB`
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) {
    return '—'
  }

  if (ms < 1000) {
    return `${Math.round(ms)} ms`
  }

  return `${(ms / 1000).toFixed(2).replace('.', ',')} s`
}

export function middleTruncate(text: string, maxLength = 30): string {
  if (text.length <= maxLength) {
    return text
  }

  const keep = maxLength - 1
  const head = Math.ceil(keep * 0.6)
  const tail = keep - head

  return `${text.slice(0, head)}…${text.slice(text.length - tail)}`
}

export function shortHash(hash: string | null | undefined): string {
  if (!hash) {
    return '—'
  }

  return `${hash.slice(0, 12)}…${hash.slice(-6)}`
}
