# Solución de Errores Frecuentes — Doppler

## 1. Error CORS al subir desde el navegador (`r2_network_error` o preflight OPTIONS 403)
- **Causa:** El bucket privado de Cloudflare R2 no tiene configurada la política CORS para `http://localhost:4321` o el token de `.env` no tiene permiso `PutBucketCors` (`Admin Read & Write`).
- **Solución:** Aplica la política de [config/r2-cors.json](../config/r2-cors.json) en **Cloudflare Dashboard → R2 → tu bucket → Settings → CORS Policy** sin eliminar reglas ajenas y vuelve a ejecutar `python3 scripts/r2_check.py`.

## 2. `Permission denied` al cargar `/models/model.pt` en el contenedor `inference`
- **Causa:** El checkpoint en el host tiene permisos `0700` pertenecientes al usuario local (UID 1000).
- **Solución:** El `Dockerfile` de `services/inference` utiliza el usuario `doppler` con UID `1000` para leer el montaje `:ro` sin alterar los archivos originales. Si tu UID en Linux difiere de `1000`, ajusta `user: "<tu-uid>:<tu-gid>"` en `docker-compose.yml`.

## 3. Archivo WAV rechazado por duración menor a 3,0 s (`short_clip: true`)
- **Causa:** Comportamiento intencional del contrato (`drop_short_clip`). El modelo fue entrenado exclusivamente sobre ventanas completas de 3,0 s a 16 000 Hz y no rellena audios cortos con silencio.
- **Solución:** Utiliza un archivo WAV de al menos 3,0 segundos.

## 4. `queue_full` (HTTP 429)
- **Causa:** Se alcanzó `MAX_QUEUE_DEPTH` (por defecto 16 trabajos pendientes/en curso) mientras el despachador procesa con `MAX_CONCURRENT_INFERENCE=1`.
- **Solución:** Espera unos segundos a que se vacíe la cola o ajusta `MAX_QUEUE_DEPTH` en `.env` y reinicia `docker compose up -d api`.

## 5. `config_error` o `r2_reachable: false` en `/api/health`
- **Causa:** Faltan variables `R2_*` en `.env`, contienen valores plantilla `replace_with_*`, o no hay salida de red hacia `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`.
- **Solución:** Verifica `.env` contra `.env.example` y ejecuta `python3 scripts/r2_check.py`.

## 6. Trabajo interrumpido al reiniciar el contenedor `api`
- **Comportamiento esperado:** Al arrancar, `doppler-api` ejecuta `recover_interrupted_jobs()` y devuelve cualquier trabajo en estado `analyzing` al estado `queued` en SQLite para reintentarlo automáticamente.

## 7. HTTP `503 maintenance_mode` al intentar subir un WAV
- **Causa:** El modo mantenimiento está activado (desde `/mantenimiento` o durante una ejecución de `scripts/model_manager.py activate`).
- **Solución:** Espera a que concluya la actualización o desactívalo en `/mantenimiento` (o `POST /api/admin/maintenance` con `{"enabled": false}`).

## 8. HTTP `503` o `401` al acceder a `/mantenimiento` o `/api/admin/*`
- **Causa:** Si devuelve `503`, `ADMIN_API_TOKEN` no está configurado en `.env` o conserva un valor plantilla `replace_with_*`. Si devuelve `401`, el token ingresado no coincide con el configurado en el contenedor `api`.
- **Solución:** Define un token aleatorio de 64 caracteres hex en `.env` (`ADMIN_API_TOKEN=...`) y recrea el servicio `docker compose up -d api`.
