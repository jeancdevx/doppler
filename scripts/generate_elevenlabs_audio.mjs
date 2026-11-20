#!/usr/bin/env node
/**
 * Genera la locución en español con timestamps exactos por palabra y la pista de
 * ambiente/SFX usando el SDK oficial `@elevenlabs/elevenlabs-js`.
 *
 * Lee ELEVENLABS_API_KEY automáticamente desde `.env` al ejecutarse con:
 *   node --env-file=.env scripts/generate_elevenlabs_audio.mjs
 *
 * Nunca imprime secretos ni guarda claves en código.
 */

import fs from 'node:fs/promises'
import path from 'node:path'

import { ElevenLabsClient } from '@elevenlabs/elevenlabs-js'

const OUT_DIR = path.resolve('media/doppler-promo/assets/audio')

// Pre-made voice compatible con cuentas gratuitas de ElevenLabs (George: narrador documental claro y sobrio)
const VOICE_ID = 'JBFqnCBsd6RMkjVDRZzb'

// Guion en 8 segmentos narrados en español (~55-58 s totales), estructurado para que cada
// escena arranque sincronizada exactamente con su frase ancla.
const SEGMENTS = [
  {
    id: 'hook',
    text: 'En medio del tráfico urbano, una sirena puede esconderse entre el ruido. ¿Cómo saber exactamente cuándo aparece… y demostrarlo?'
  },
  {
    id: 'tension',
    text: 'Una etiqueta aislada sin pruebas nunca basta. Un score sigmoide no es un porcentaje de confianza.'
  },
  {
    id: 'reveal',
    text: 'Presentamos Doppler: un instrumento acústico de detección de sirenas diseñado para llevar cada audio WAV del ruido a la señal.'
  },
  {
    id: 'upload_r2',
    text: 'Arrastras tu archivo WAV. El navegador valida la cabecera al instante y lo sube directo a Cloudflare R2 privado, sin abrir el bucket ni exponer credenciales.'
  },
  {
    id: 'pipeline',
    text: 'Rust verifica el tamaño real y lo envía a PyTorch en CPU. El audio se normaliza a dieciséis mil hercios, se divide en ventanas solapadas de tres segundos y entra como matriz Log-Mel a ResNet dieciocho.'
  },
  {
    id: 'payoff',
    text: 'En milisegundos, cada ventana muestra su score frente al umbral congelado cero punto seis cinco cuatro ocho. Escuchas el audio, observas el espectrograma real y recorres cada ventana sin caja negra.'
  },
  {
    id: 'privacy',
    text: 'Exporta resultados reproducibles en JSON o CSV con hashes verificados, o elimina tu archivo de R2 y SQLite en un clic. Si no, se purga automáticamente a las veinticuatro horas.'
  },
  {
    id: 'endcard',
    text: 'Doppler. Escucha, observa y contrasta. Del ruido a la señal.'
  }
]

function extractWordsFromAlignment(alignment) {
  if (!alignment || !Array.isArray(alignment.characters)) {
    return []
  }

  const chars = alignment.characters
  const starts = alignment.characterStartTimesSeconds || []
  const ends = alignment.characterEndTimesSeconds || []

  const words = []
  let buf = ''
  let wordStart = null
  let wordEnd = null

  for (let i = 0; i < chars.length; i += 1) {
    const ch = chars[i]

    if (/\s/.test(ch)) {
      if (buf.length > 0 && wordStart !== null && wordEnd !== null) {
        words.push({ text: buf, start: wordStart, end: wordEnd })
      }

      buf = ''
      wordStart = null
      wordEnd = null
    } else {
      if (wordStart === null) {
        wordStart = starts[i] ?? 0
      }

      wordEnd = ends[i] ?? wordStart + 0.1
      buf += ch
    }
  }

  if (buf.length > 0 && wordStart !== null && wordEnd !== null) {
    words.push({ text: buf, start: wordStart, end: wordEnd })
  }

  return words
}

async function streamToBuffer(webStreamOrIterable) {
  const chunks = []

  for await (const chunk of webStreamOrIterable) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
  }

  return Buffer.concat(chunks)
}

async function main() {
  if (!process.env.ELEVENLABS_API_KEY) {
    throw new Error(
      'ELEVENLABS_API_KEY no está cargada. Ejecuta con: node --env-file=.env scripts/generate_elevenlabs_audio.mjs'
    )
  }

  await fs.mkdir(OUT_DIR, { recursive: true })

  const client = new ElevenLabsClient()

  // Un solo texto continuo unido con pausas naturales garantiza prosodia uniforme y un solo request limpio
  const fullText = SEGMENTS.map(s => s.text).join(' ')

  console.log(
    `Generando locución en español (${fullText.length} caracteres) con ElevenLabs...`
  )

  let response
  let modelUsed = 'eleven_multilingual_v2'

  try {
    response = await client.textToSpeech.convertWithTimestamps(VOICE_ID, {
      text: fullText,
      modelId: modelUsed,
      outputFormat: 'mp3_44100_128',
      voiceSettings: {
        stability: 0.56,
        similarityBoost: 0.78,
        style: 0.15,
        useSpeakerBoost: true
      }
    })
  } catch (err) {
    console.warn(
      `Reintentando con eleven_v4 tras aviso en ${modelUsed}: ${err.message}`
    )
    modelUsed = 'eleven_v4'
    response = await client.textToSpeech.convertWithTimestamps(VOICE_ID, {
      text: fullText,
      modelId: modelUsed,
      outputFormat: 'mp3_44100_128',
      voiceSettings: {
        stability: 0.55,
        similarityBoost: 0.78
      }
    })
  }

  const audioB64 = response.audioBase64 || response.audio_base64

  if (!audioB64) {
    throw new Error('La respuesta de ElevenLabs no incluyó audioBase64.')
  }

  const voicePath = path.join(OUT_DIR, 'voiceover_es.mp3')

  await fs.writeFile(voicePath, Buffer.from(audioB64, 'base64'))

  const alignment = response.normalizedAlignment || response.alignment
  const words = extractWordsFromAlignment(alignment)

  // Asigna cada segmento a sus palabras por conteo exacto de tokens
  const segmentTimings = []
  let cursor = 0

  for (const seg of SEGMENTS) {
    const segTokenCount = seg.text.trim().split(/\s+/).length
    const slice = words.slice(cursor, cursor + segTokenCount)

    cursor += segTokenCount
    const start = slice[0]?.start ?? segmentTimings.at(-1)?.end ?? 0
    const end = slice.at(-1)?.end ?? start + 4.0

    segmentTimings.push({
      id: seg.id,
      text: seg.text,
      start: Number(start.toFixed(3)),
      end: Number(end.toFixed(3)),
      words: slice.map((w, idx) => ({
        id: `${seg.id}_w${idx}`,
        text: w.text,
        start: Number(w.start.toFixed(3)),
        end: Number(w.end.toFixed(3))
      }))
    })
  }

  const totalVoiceDuration = Number(
    (words.at(-1)?.end ?? segmentTimings.at(-1)?.end ?? 56.0).toFixed(3)
  )

  const manifest = {
    modelId: modelUsed,
    voiceId: VOICE_ID,
    characterCount: fullText.length,
    totalVoiceDuration,
    wordCount: words.length,
    segments: segmentTimings,
    words: words.map((w, i) => ({
      id: `w${i}`,
      text: w.text,
      start: Number(w.start.toFixed(3)),
      end: Number(w.end.toFixed(3))
    }))
  }

  const tsPath = path.join(OUT_DIR, 'voiceover_timestamps.json')

  await fs.writeFile(tsPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
  console.log(
    `Locución guardada: ${voicePath} (${totalVoiceDuration} s, ${words.length} palabras, modelo ${modelUsed})`
  )

  // Genera cama musical minimalista de 20 s en bucle y un impacto suave de clímax mediante Sound Effects
  try {
    console.log('Generando cama musical minimalista en bucle (20 s)...')
    const bedStream = await client.textToSoundEffects.convert({
      text: 'Minimalist clean electronic documentary background pulse, warm soft sub bass and subtle rhythmic analog synth arpeggio, steady 112 bpm, modern technology laboratory atmosphere, no vocals, smooth and calm',
      modelId: 'eleven_text_to_sound_v3',
      durationSeconds: 20.0,
      promptInfluence: 0.45,
      loop: true,
      outputFormat: 'mp3_44100_128'
    })
    const bedBuf = await streamToBuffer(bedStream)
    const bedPath = path.join(OUT_DIR, 'bed_pulse.mp3')

    await fs.writeFile(bedPath, bedBuf)
    console.log(`Cama musical guardada: ${bedPath} (${bedBuf.length} bytes)`)
  } catch (err) {
    console.warn(
      `No se pudo generar la cama musical con SFX v3: ${err.message}`
    )
  }

  try {
    console.log('Generando efecto suave de clímax acústico (2.0 s)...')
    const sfxStream = await client.textToSoundEffects.convert({
      text: 'Clean futuristic soft precision sonar sweep rising gently into a subtle warm low impact hit, laboratory interface confirmation',
      modelId: 'eleven_text_to_sound_v3',
      durationSeconds: 2.0,
      promptInfluence: 0.55,
      loop: false,
      outputFormat: 'mp3_44100_128'
    })
    const sfxBuf = await streamToBuffer(sfxStream)
    const sfxPath = path.join(OUT_DIR, 'sfx_payoff.mp3')

    await fs.writeFile(sfxPath, sfxBuf)
    console.log(`SFX guardado: ${sfxPath} (${sfxBuf.length} bytes)`)
  } catch (err) {
    console.warn(`No se pudo generar el SFX de clímax: ${err.message}`)
  }
}

main().catch(err => {
  console.error('Error generando audio con ElevenLabs:', err.message || err)
  process.exit(1)
})
