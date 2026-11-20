# Guía de Pruebas — Doppler

Todas las pruebas técnicas automatizadas utilizan **fixtures WAV sintéticas** generadas programáticamente. Estas fixtures validan paridad numérica, manejo de formatos, integración con R2 y experiencia de usuario, pero **no representan grabaciones reales ni evaluación de desempeño predictivo**.

## 1. Paridad independiente con notebooks y matriz de archivos WAV (offline)

Ejecuta `ruff` y `pytest` dentro del contenedor de inferencia **sin red (`--network none`)** para probar simultáneamente la carga offline sin descargar pesos ImageNet:

```bash
docker run --rm --network none \
  -v "$(pwd)/Doppler_Espectro_Brand_Kit/model:/models:ro" \
  doppler-inference:1.0.0 \
  sh -c "ruff check --no-cache src tests && pytest -v -o cache_dir=/tmp/pytest_cache tests/test_parity_and_files.py"
```

Cobertura:
- Comparación contra `services/inference/tests/notebook_reference.py` (implementación independiente extraída de `00_preparacion_insumos.ipynb` y `05_resnet18.ipynb`, sin importar `doppler_inference`).
- Mono, estéreo, 8 / 16 / 22,05 / 44,1 / 48 kHz y silencio puro.
- Clip corto `< 3,0 s` (sin relleno silencioso), límites exactos `3,0 s` / `4,49 s` / `4,5 s` y cola incompleta `5,2 s`.
- Archivo vacío, cabecera falsa, WAV corrupto y exceso de duración (`> 120 s`).

## 2. Pruebas unitarias de Rust (API)

Se ejecutan automáticamente al construir la imagen `doppler-api` (`cargo test --lib --tests`), cubriendo firma/verificación HMAC de sesiones, saneado de nombres de archivo y unión de intervalos positivos solapados.

## 3. Verificación real de Cloudflare R2

```bash
python3 scripts/r2_check.py
```

## 4. Integración completa extremo a extremo (Caddy + Rust + R2 real + Python + SQLite)

Con el stack levantado (`docker compose up -d`):

```bash
python3 tests/integration/test_api_and_r2.py
```

Valida `/api/health`, rechazos de tamaño/extensión, ciclo completo `PUT` a R2 → confirmación idempotente → inferencia → descarga temporal autorizada + SHA-256 → exportación JSON/CSV, aislamiento entre sesiones, clip corto, WAV corrupto, cola con concurrencia 1, persistencia tras `docker compose restart api` y eliminación completa en R2 y SQLite.

## 5. Calidad de código y pruebas de interfaz (Astro + Svelte + Playwright)

```bash
pnpm run check:web
pnpm run format:check
pnpm run lint
pnpm run test:e2e
```

Playwright verifica escritorio `1440×900`, móvil `390×844` sin desbordamiento horizontal, navegación por teclado y foco, tema claro/oscuro del estudio, `prefers-reduced-motion: reduce`, error recuperable con archivo falso, página 404 y flujo E2E completo desde el navegador hacia R2 (este último requiere CORS configurado en el bucket).

## 6. Pruebas del Capítulo 10 (Monitoreo, Drift, Retroalimentación y Actualización de Modelo)

```bash
# Integración real: /api/ready (200/503), auth X-Admin-Token (401), incidentes y auto-recuperación,
# telemetría 30 d tras borrado 24 h, aislamiento y máquina de estados de feedback, modo mantenimiento
python3 tests/integration/test_maintenance_and_feedback.py

# Experimentos controlados de drift (referencia sintética + 5 escenarios con semilla fija)
python3 scripts/drift_engine.py --out-dir /tmp/doppler_drift_test

# Ensayo controlado de validación offline, rechazo de paquetes inválidos, activación y rollback automático
python3 scripts/model_manager.py drill

# E2E Playwright del formulario de retroalimentación y consola /mantenimiento (escritorio + móvil)
pnpm exec playwright test tests/e2e/maintenance.spec.ts
```
