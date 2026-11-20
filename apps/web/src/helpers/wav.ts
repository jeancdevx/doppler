import { DOPPLER_DEFAULTS } from '@/constants/doppler'

export interface LocalWavCheck {
  valid: boolean
  errorCode?: string
  errorMessage?: string
  durationSeconds?: number
  sampleRate?: number
  channels?: number
  isShortClip?: boolean
}

export interface ComputedSpectrogram {
  frames: number
  bins: number
  magnitudes: Float32Array
  sampleRate: number
  fftSize: number
  hopSize: number
  maxFrequencyHz: number
  durationSeconds: number
}

export async function prevalidateWavFile(
  file: File,
  maxBytes: number = DOPPLER_DEFAULTS.maxFileBytes,
  maxDurationSeconds: number = DOPPLER_DEFAULTS.maxDurationSeconds
): Promise<LocalWavCheck> {
  if (!/\.wav$/i.test(file.name)) {
    return {
      valid: false,
      errorCode: 'invalid_extension',
      errorMessage: 'Selecciona un archivo con extensión .wav.'
    }
  }

  if (file.size === 0) {
    return {
      valid: false,
      errorCode: 'empty_file',
      errorMessage: 'El archivo seleccionado está vacío (0 bytes).'
    }
  }

  if (file.size > maxBytes) {
    return {
      valid: false,
      errorCode: 'size_exceeded',
      errorMessage: `El archivo supera el límite permitido de ${Math.round(maxBytes / (1024 * 1024))} MiB.`
    }
  }

  const headerBuf = await file.slice(0, 16).arrayBuffer()
  const header = new Uint8Array(headerBuf)

  if (header.length < 12) {
    return {
      valid: false,
      errorCode: 'invalid_header',
      errorMessage:
        'El archivo es demasiado pequeño para contener una cabecera WAV.'
    }
  }

  const riff = String.fromCharCode(header[0], header[1], header[2], header[3])
  const wave = String.fromCharCode(header[8], header[9], header[10], header[11])

  if ((riff !== 'RIFF' && riff !== 'RF64') || wave !== 'WAVE') {
    return {
      valid: false,
      errorCode: 'invalid_format',
      errorMessage:
        'La extensión es .wav pero la cabecera binaria no corresponde a un WAV RIFF/WAVE válido.'
    }
  }

  try {
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext
    const ctx = new AudioCtx()

    try {
      const fullBuffer = await file.arrayBuffer()
      const decoded = await ctx.decodeAudioData(fullBuffer)

      if (decoded.duration > maxDurationSeconds) {
        return {
          valid: false,
          errorCode: 'duration_exceeded',
          errorMessage: `La duración (${decoded.duration.toFixed(1).replace('.', ',')} s) excede el máximo de ${maxDurationSeconds} s.`
        }
      }

      return {
        valid: true,
        durationSeconds: decoded.duration,
        sampleRate: decoded.sampleRate,
        channels: decoded.numberOfChannels,
        isShortClip: decoded.duration < DOPPLER_DEFAULTS.minWindowSeconds
      }
    } finally {
      await ctx.close()
    }
  } catch {
    return {
      valid: false,
      errorCode: 'decode_error',
      errorMessage:
        'No se pudo decodificar este archivo WAV en el navegador. Verifica que sea un WAV PCM o flotante íntegro.'
    }
  }
}

export function extractWaveformPeaks(
  buffer: AudioBuffer,
  bars = 320
): Float32Array {
  const channels = buffer.numberOfChannels
  const length = buffer.length
  const peaks = new Float32Array(bars)

  if (length === 0 || channels === 0) {
    return peaks
  }

  const channelData: Float32Array[] = []

  for (let c = 0; c < channels; c += 1) {
    channelData.push(buffer.getChannelData(c))
  }

  const samplesPerBar = Math.max(1, Math.floor(length / bars))
  const stride = Math.max(1, Math.floor(samplesPerBar / 64))

  for (let i = 0; i < bars; i += 1) {
    const start = i * samplesPerBar
    const end = Math.min(length, start + samplesPerBar)
    let peak = 0

    for (let s = start; s < end; s += stride) {
      let sum = 0

      for (let c = 0; c < channels; c += 1) {
        sum += channelData[c][s]
      }

      const monoSample = Math.abs(sum / channels)

      if (monoSample > peak) {
        peak = monoSample
      }
    }

    peaks[i] = Math.min(1, peak)
  }

  return peaks
}

function fftRadix2(re: Float32Array, im: Float32Array): void {
  const n = re.length
  let j = 0

  for (let i = 1; i < n; i += 1) {
    let bit = n >> 1

    while (j & bit) {
      j ^= bit
      bit >>= 1
    }

    j ^= bit

    if (i < j) {
      const tr = re[i]
      const ti = im[i]

      re[i] = re[j]
      im[i] = im[j]
      re[j] = tr
      im[j] = ti
    }
  }

  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len
    const wLenRe = Math.cos(ang)
    const wLenIm = Math.sin(ang)

    for (let i = 0; i < n; i += len) {
      let wRe = 1
      let wIm = 0
      const half = len >> 1

      for (let k = 0; k < half; k += 1) {
        const uRe = re[i + k]
        const uIm = im[i + k]
        const vRe = re[i + k + half] * wRe - im[i + k + half] * wIm
        const vIm = re[i + k + half] * wIm + im[i + k + half] * wRe

        re[i + k] = uRe + vRe
        im[i + k] = uIm + vIm
        re[i + k + half] = uRe - vRe
        im[i + k + half] = uIm - vIm

        const nextRe = wRe * wLenRe - wIm * wLenIm

        wIm = wRe * wLenIm + wIm * wLenRe
        wRe = nextRe
      }
    }
  }
}

export function computeRealSpectrogram(
  buffer: AudioBuffer,
  maxFrames = 240,
  displayBins = 64
): ComputedSpectrogram {
  const channels = buffer.numberOfChannels
  const length = buffer.length
  const sr = buffer.sampleRate
  const fftSize = 1024
  const mono = new Float32Array(length)

  for (let c = 0; c < channels; c += 1) {
    const data = buffer.getChannelData(c)

    for (let i = 0; i < length; i += 1) {
      mono[i] += data[i] / channels
    }
  }

  const hopSize = Math.max(
    256,
    Math.floor(Math.max(1, length - fftSize) / maxFrames)
  )
  const frames = Math.max(
    1,
    Math.min(maxFrames, Math.floor((length - fftSize) / hopSize) + 1)
  )

  const hann = new Float32Array(fftSize)

  for (let i = 0; i < fftSize; i += 1) {
    hann[i] = 0.5 * (1 - Math.cos((2 * Math.PI * i) / fftSize))
  }

  const nyquist = sr / 2
  const maxFrequencyHz = Math.min(8000, nyquist)
  const maxBin = Math.max(
    displayBins,
    Math.min(
      fftSize / 2,
      Math.floor((maxFrequencyHz / nyquist) * (fftSize / 2))
    )
  )

  const rawPower = new Float32Array(frames * displayBins)
  const re = new Float32Array(fftSize)
  const im = new Float32Array(fftSize)
  let maxPower = 1e-10

  // Mapeo logarítmico-Mel aproximado para visualizar 20 Hz - 8000 Hz en 64 bandas
  const binEdges = new Int32Array(displayBins + 1)
  const hzToMel = (hz: number) => 2595 * Math.log10(1 + hz / 700)
  const melToHz = (mel: number) => 700 * (10 ** (mel / 2595) - 1)
  const melMin = hzToMel(20)
  const melMax = hzToMel(maxFrequencyHz)

  for (let b = 0; b <= displayBins; b += 1) {
    const hz = melToHz(melMin + ((melMax - melMin) * b) / displayBins)
    const idx = Math.round((hz / nyquist) * (fftSize / 2))

    binEdges[b] = Math.max(1, Math.min(maxBin, idx))
  }

  for (let f = 0; f < frames; f += 1) {
    const offset = f * hopSize

    re.fill(0)
    im.fill(0)

    for (let i = 0; i < fftSize && offset + i < length; i += 1) {
      re[i] = mono[offset + i] * hann[i]
    }

    fftRadix2(re, im)

    for (let b = 0; b < displayBins; b += 1) {
      const bStart = binEdges[b]
      const bEnd = Math.max(bStart + 1, binEdges[b + 1])
      let sum = 0

      for (let k = bStart; k < bEnd; k += 1) {
        sum += re[k] * re[k] + im[k] * im[k]
      }

      const avg = sum / (bEnd - bStart)

      rawPower[f * displayBins + b] = avg

      if (avg > maxPower) {
        maxPower = avg
      }
    }
  }

  const magnitudes = new Float32Array(frames * displayBins)
  const topDb = 80

  for (let i = 0; i < rawPower.length; i += 1) {
    const db = 10 * Math.log10(Math.max(rawPower[i], 1e-10) / maxPower)
    const clamped = Math.max(-topDb, Math.min(0, db))

    magnitudes[i] = (clamped + topDb) / topDb
  }

  return {
    frames,
    bins: displayBins,
    magnitudes,
    sampleRate: sr,
    fftSize,
    hopSize,
    maxFrequencyHz,
    durationSeconds: buffer.duration
  }
}
