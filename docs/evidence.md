# Guía de Generación y Empaquetado de Evidencias Académicas

Las evidencias de validación local para sustentar posteriormente los apartados **9.1**, **9.2** y **9.3** se generan ejecutando el sistema real con un único comando reproducible.

## 1. Generar una ejecución completa de evidencias

Con el stack en marcha (`docker compose up -d`):

```bash
pnpm run evidence:generate
# equivalente directo:
python3 scripts/generate_evidence.py --observations 30
```

Crea la carpeta `evidence/<run_id>/` con:
- `manifest.json`: fecha UTC, revisión Git, configuración depurada sin secretos, hashes SHA-256 y estado de comprobaciones.
- `entorno_y_versiones.json`: hardware, sistema, versiones y hashes de `model.pt`, `inference.json` y notebooks.
- `paridad_notebook.{json,csv}`: informe independiente de paridad numérica.
- `comprobacion_r2.json`: verificación real de Cloudflare R2 sin credenciales ni URLs firmadas completas.
- `pruebas_integracion.json` y `etapas_pipeline_r2.csv`: flujo real extremo a extremo y desglose por etapa.
- `benchmark_cpu_observaciones.csv`, `benchmark_cpu_resumen.{json,csv}`: `n = 30` ejecuciones calientes por cada duración (`3 s`, `6 s`, `15 s`, `30 s`), separadas de arranque y calentamiento.
- `memoria_servicios.csv` y `memoria_servicios_resumen.json`: muestreo `docker stats` cada 1 s en reposo y bajo carga.
- `pruebas_interfaz.json` y `capturas/*.png`: reporte Playwright y capturas reales de la aplicación ejecutada.
- `diagramas/*.{svg,png}` y `graficas/*.{svg,png}`: diagramas de arquitectura/secuencia y gráficas de latencia, etapas y memoria en español.
- `informe_validacion_local.md` e `indice_figuras_y_tablas.md`.

## 2. Empaquetar en ZIP con manifiesto SHA-256

```bash
pnpm run evidence:pack
# o indicando una carpeta concreta:
python3 scripts/pack_evidence.py evidence/<run_id>
```

El empaquetador audita automáticamente que no existan secretos, cookies, URLs firmadas completas, archivos `.env`, `.pt` ni `.wav` privados dentro de la carpeta, genera `SHA256SUMS.txt` interno, crea `evidence/<run_id>.zip` y escribe `evidence/<run_id>.zip.sha256`.

## 3. Verificación de integridad del ZIP

```bash
sha256sum -c evidence/<run_id>.zip.sha256
```
