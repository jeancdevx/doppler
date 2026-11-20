import fs from 'node:fs'
import path from 'node:path'

import { expect, test } from '@playwright/test'

const SCREENSHOT_DIR =
  process.env.DOPPLER_SCREENSHOT_DIR || 'test-results/screenshots'

function ensureDir(dir: string) {
  fs.mkdirSync(dir, { recursive: true })
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
    let val = 0

    if (siren) {
      const freq = 1050 + 400 * Math.sin(2 * Math.PI * 0.45 * t)

      phase += (2 * Math.PI * freq) / sr
      val = 0.65 * Math.sin(phase) + 0.15 * Math.sin(2 * phase)
    } else {
      val = 0.12 * Math.sin(2 * Math.PI * 140 * t)
    }

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

test.describe('Doppler interfaz, accesibilidad y flujo completo', () => {
  test.beforeAll(() => {
    ensureDir(SCREENSHOT_DIR)
  })

  test('escritorio: carga limpia, sin errores de consola, foco por teclado y cambio de tema', async ({
    page
  }) => {
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

    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/', { waitUntil: 'networkidle' })

    await expect(page.locator('#hero-title')).toContainText('Del ruido')
    await expect(page.locator('#doppler-workbench')).toBeVisible()
    await expect(page.locator('#doppler-workbench')).toHaveAttribute(
      'data-studio-theme',
      'dark'
    )

    // Verifica ausencia de desbordamiento horizontal en escritorio
    const overflowDesktop = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1
    )

    expect(overflowDesktop).toBe(false)

    // Captura real de entrada + recorrido scroll + estudio en tema oscuro
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '01_escritorio_entrada.png'),
      fullPage: false
    })

    await page.locator('#recorrido').scrollIntoViewIfNeeded()
    await page.waitForTimeout(350)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '01b_recorrido_acustico.png'),
      fullPage: false
    })

    await page.locator('#studio').scrollIntoViewIfNeeded()
    await page.waitForTimeout(300)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '02_estudio_vacio_oscuro.png'),
      fullPage: false
    })

    await page.locator('#contrato').scrollIntoViewIfNeeded()
    await page.waitForTimeout(350)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '07_bento_arquitectura.png'),
      fullPage: false
    })

    await page.locator('#faq').scrollIntoViewIfNeeded()
    await page.waitForTimeout(350)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '08_faq_redisenado.png'),
      fullPage: false
    })

    // Navegación por teclado: primer Tab enfoca el enlace "Saltar al contenido principal"
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.keyboard.press('Tab')
    const focusedText = await page.evaluate(
      () => document.activeElement?.textContent?.trim() || ''
    )

    expect(focusedText).toContain('Saltar al contenido')

    // Cambio de tema claro/oscuro en el estudio
    const themeToggle = page.getByRole('button', {
      name: /Cambiar estudio a tema claro/i
    })

    await themeToggle.click()
    await expect(page.locator('#doppler-workbench')).toHaveAttribute(
      'data-studio-theme',
      'light'
    )
    await page.locator('#studio').scrollIntoViewIfNeeded()
    await page.waitForTimeout(200)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '03_estudio_tema_claro.png'),
      fullPage: false
    })

    // Regresar a tema oscuro
    await page
      .getByRole('button', { name: /Cambiar estudio a tema oscuro/i })
      .click()
    await expect(page.locator('#doppler-workbench')).toHaveAttribute(
      'data-studio-theme',
      'dark'
    )

    // Error recuperable con archivo falso (.wav con contenido de texto)
    const fileInput = page.locator('#doppler-wav-input')

    await fileInput.setInputFiles({
      name: 'falso_audio.wav',
      mimeType: 'audio/wav',
      buffer: Buffer.from('esto no es un archivo wav valido')
    })

    await expect(page.getByRole('alert')).toContainText(/cabecera/i)

    expect(pageErrors).toEqual([])
    expect(consoleErrors).toEqual([])
  })

  test('móvil 390px y prefers-reduced-motion: sin desbordamiento ni errores', async ({
    page
  }) => {
    const pageErrors: string[] = []

    page.on('pageerror', err => pageErrors.push(err.message))

    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/', { waitUntil: 'networkidle' })

    const overflowMobile = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1
    )

    expect(overflowMobile).toBe(false)

    // Comprobar que el CTA principal es visible en la primera pantalla
    await expect(page.locator('#hero-upload-cta')).toBeInViewport()

    // Comprobar menú móvil accesible
    await page.locator('#mobile-menu-toggle').click()
    await expect(page.locator('#mobile-nav-drawer')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.locator('#mobile-nav-drawer')).toBeHidden()

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '04_movil_390px.png'),
      fullPage: false
    })

    // Verificar página 404 personalizada
    await page.goto('/ruta-inexistente-doppler', { waitUntil: 'networkidle' })
    await expect(page.locator('main')).toContainText('ERROR 404')

    expect(pageErrors).toEqual([])
  })

  test('flujo E2E completo desde interfaz hacia R2 real e inferencia', async ({
    page
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/', { waitUntil: 'networkidle' })

    const wavBuffer = buildSyntheticWavBuffer(6.0, 16000, true)

    await page.locator('#doppler-wav-input').setInputFiles({
      name: 'sirena_sintetica_e2e.wav',
      mimeType: 'audio/wav',
      buffer: wavBuffer
    })

    // Esperar a que complete el análisis real (o falle explícitamente por CORS)
    const completedBadge = page.getByText(
      /ventana\(s\) con sirena|Sin detecciones de sirena/i
    )
    const alertBox = page.getByRole('alert')

    await expect(completedBadge.or(alertBox)).toBeVisible({ timeout: 45_000 })

    if (await alertBox.isVisible()) {
      const msg = await alertBox.textContent()

      throw new Error(`Fallo en subida directa navegador -> R2: ${msg}`)
    }

    await expect(page.locator('table tbody tr')).toHaveCount(3)

    await page.locator('#studio').scrollIntoViewIfNeeded()
    await page.waitForTimeout(300)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '05_estudio_resultado_real.png'),
      fullPage: false
    })

    // Cambiar a pestaña de espectrograma calculado
    await page.getByRole('tab', { name: /Espectrograma calculado/i }).click()
    await page.waitForTimeout(250)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '06_estudio_espectrograma_real.png'),
      fullPage: false
    })

    // Seleccionar explícitamente la ventana #2 (index 1) y #3 (index 2) y verificar que NO retrocede a la anterior solapada
    const row2 = page.locator('table tbody tr').nth(1)
    const row3 = page.locator('table tbody tr').nth(2)

    await row2.click()
    await expect(row2).toHaveAttribute('data-selected', 'true')
    await expect(page.locator('#doppler-workbench')).toContainText(
      '1,5 s a 4,5 s'
    )

    await row3.click()
    await expect(row3).toHaveAttribute('data-selected', 'true')
    await expect(page.locator('#doppler-workbench')).toContainText(
      '3,0 s a 6,0 s'
    )

    // Verificar botones de exportación JSON y CSV visibles
    await expect(page.getByRole('button', { name: 'JSON' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'CSV' })).toBeVisible()

    // Eliminar trabajo mediante diálogo de confirmación accesible
    await page
      .getByRole('button', { name: /Eliminar archivo y resultados/i })
      .click()
    await page
      .getByRole('button', { name: /Eliminar permanentemente/i })
      .click()
    await expect(
      page.getByText(/Arrastra un archivo WAV o selecciónalo/i)
    ).toBeVisible()
  })
})
