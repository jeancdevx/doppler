import fs from 'node:fs'
import path from 'node:path'

import { expect, test } from '@playwright/test'

const SCREENSHOT_DIR =
  process.env.DOPPLER_MAINT_SCREENSHOT_DIR ||
  'test-results/maintenance-screenshots'

function ensureDir(dir: string) {
  fs.mkdirSync(dir, { recursive: true })
}

function readAdminTokenFromEnv(): string {
  if (process.env.ADMIN_API_TOKEN) {
    return process.env.ADMIN_API_TOKEN
  }

  const envPath = path.resolve(process.cwd(), '.env')

  if (fs.existsSync(envPath)) {
    for (const line of fs.readFileSync(envPath, 'utf-8').split(/\r?\n/)) {
      const trimmed = line.trim()

      if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) {
        continue
      }

      const idx = trimmed.indexOf('=')
      const k = trimmed.slice(0, idx).trim()
      const v = trimmed
        .slice(idx + 1)
        .trim()
        .replace(/^['"]|['"]$/g, '')

      if (k === 'ADMIN_API_TOKEN') {
        return v
      }
    }
  }

  throw new Error('ADMIN_API_TOKEN no encontrado en entorno ni en .env')
}

function buildSyntheticWavBuffer(
  durationSec = 6.0,
  sr = 16000,
  siren = true
): Buffer {
  const n = Math.round(durationSec * sr)
  const pcm = Buffer.alloc(n * 2)
  let phase = 0

  for (let i = 0; i < n; i += 1) {
    const t = i / sr
    const freq = siren ? 1050 + 400 * Math.sin(2 * Math.PI * 0.45 * t) : 140

    phase += (2 * Math.PI * freq) / sr
    const val = siren
      ? 0.65 * Math.sin(phase) + 0.15 * Math.sin(2 * phase)
      : 0.12 * Math.sin(phase)
    const s16 = Math.max(-32767, Math.min(32767, Math.round(val * 32767)))

    pcm.writeInt16LE(s16, i * 2)
  }

  const header = Buffer.alloc(44)

  header.write('RIFF', 0)
  header.writeUInt32LE(36 + pcm.length, 4)
  header.write('WAVE', 8)
  header.write('fmt ', 12)
  header.writeUInt32LE(16, 16)
  header.writeUInt16LE(1, 20)
  header.writeUInt16LE(1, 22)
  header.writeUInt32LE(sr, 24)
  header.writeUInt32LE(sr * 2, 28)
  header.writeUInt16LE(2, 32)
  header.writeUInt16LE(16, 34)
  header.write('data', 36)
  header.writeUInt32LE(pcm.length, 40)

  return Buffer.concat([header, pcm])
}

test.describe('Capítulo 10: Retroalimentación y consola /mantenimiento', () => {
  test.beforeAll(() => {
    ensureDir(SCREENSHOT_DIR)
  })

  test('estudio: enviar reporte de retroalimentación y revisar consola /mantenimiento en escritorio y móvil', async ({
    page
  }) => {
    const adminToken = readAdminTokenFromEnv()
    const consoleErrors: string[] = []
    const pageErrors: string[] = []

    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })
    page.on('pageerror', err => {
      pageErrors.push(err.message)
    })

    // 1. Subir WAV sintético y enviar reporte desde el formulario integrado del estudio
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/', { waitUntil: 'networkidle' })

    await page.locator('#doppler-wav-input').setInputFiles({
      name: 'sirena_sintetica_feedback_e2e.wav',
      mimeType: 'audio/wav',
      buffer: buildSyntheticWavBuffer(6.0, 16000, true)
    })

    const completedBadge = page.getByText(
      /ventana\(s\) con sirena|Sin detecciones de sirena/i
    )

    await expect(completedBadge).toBeVisible({ timeout: 45_000 })

    // Seleccionar ventana 2 (index 1) y completar el formulario de retroalimentación
    await page.locator('table tbody tr').nth(1).click()
    await page.locator('#doppler-feedback-type').selectOption('false_alarm')
    await page
      .locator('#doppler-feedback-comment')
      .fill('Reporte E2E controlado sobre ventana 2 (señal sintética).')

    await page.locator('#feedback-panel-heading').scrollIntoViewIfNeeded()
    await page.waitForTimeout(250)
    await page.getByRole('button', { name: /Enviar reporte/i }).click()
    await expect(page.getByText('Recibido').first()).toBeVisible({
      timeout: 15_000
    })

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '10_estudio_retroalimentacion.png'),
      fullPage: false
    })

    // 2. Abrir /mantenimiento y comprobar acceso restringido en memoria
    await page.goto('/mantenimiento', { waitUntil: 'networkidle' })
    await expect(page.locator('#doppler-admin-token')).toBeVisible()
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '11_mantenimiento_acceso.png'),
      fullPage: false
    })

    // Autenticar (el campo es type="password" y se limpia al iniciar sesión)
    await page.locator('#doppler-admin-token').fill(adminToken)
    await page
      .getByRole('button', { name: /Ingresar a mantenimiento/i })
      .click()

    await expect(page.getByText(/Salud de dependencias en vivo/i)).toBeVisible({
      timeout: 15_000
    })

    // Verificar que el token NO se guarda en localStorage ni sessionStorage
    const storedSecrets = await page.evaluate(() => ({
      local: Object.keys(window.localStorage).filter(k =>
        k.toLowerCase().includes('token')
      ),
      session: Object.keys(window.sessionStorage).filter(k =>
        k.toLowerCase().includes('token')
      )
    }))

    expect(storedSecrets.local).toEqual([])
    expect(storedSecrets.session).toEqual([])

    const overflowDesktop = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1
    )

    expect(overflowDesktop).toBe(false)

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '12_mantenimiento_operacion.png'),
      fullPage: false
    })

    // Pestaña Drift
    await page.getByRole('tab', { name: /Detección de drift/i }).click()
    await expect(page.getByText(/Estado de representatividad/i)).toBeVisible()
    await page.waitForTimeout(200)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '13_mantenimiento_drift.png'),
      fullPage: false
    })

    // Pestaña Retroalimentación
    await page.getByRole('tab', { name: /Retroalimentación/i }).click()
    await expect(page.getByText(/Bandeja de retroalimentación/i)).toBeVisible()
    await page.waitForTimeout(200)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '14_mantenimiento_retroalimentacion.png'),
      fullPage: false
    })

    // Pestaña Modelo y despliegues
    await page.getByRole('tab', { name: /Modelo y despliegues/i }).click()
    await expect(
      page.getByText(/Artefacto activo en inferencia CPU/i)
    ).toBeVisible()
    await page.waitForTimeout(200)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '15_mantenimiento_despliegues.png'),
      fullPage: false
    })

    // 3. Vista móvil 390px sin desbordamiento horizontal
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('tab', { name: /Operación y salud/i }).click()
    await page.waitForTimeout(250)
    const overflowMobile = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1
    )

    expect(overflowMobile).toBe(false)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '16_mantenimiento_movil_390px.png'),
      fullPage: false
    })

    // 4. Volver al estudio y eliminar el trabajo sintético creado para limpiar R2
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/', { waitUntil: 'networkidle' })
    const delBtn = page.getByRole('button', {
      name: /Eliminar archivo y resultados/i
    })

    if (await delBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await delBtn.click()
      await page
        .getByRole('button', { name: /Eliminar permanentemente/i })
        .click()
    }

    expect(pageErrors).toEqual([])
    expect(consoleErrors).toEqual([])
  })
})
