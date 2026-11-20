# Arquitectura y Flujo Real de Datos — Doppler

## 1. Visión general

Doppler separa la presentación, la orquestación con almacenamiento en la nube y la inferencia acústica en tres contenedores reproducibles mediante Docker Compose en Linux Manjaro:

1. **Entrada y estáticos (`web` — Caddy 2.9.1):**
   - Sirve el frontend compilado estáticamente por **Astro 5** (incluyendo la isla interactiva **Svelte 5** y fuentes locales IBM Plex Sans/Mono).
   - Redirige `/api/*` por la red interna Docker hacia `api:8080`.
   - Publicado en `127.0.0.1:4321` (`http://localhost:4321`).
2. **API principal y despachador (`api` — Rust / Axum / Tokio / SQLite / `aws-sdk-s3`):**
   - Gestiona sesiones anónimas mediante cookie `HttpOnly`, `SameSite=Lax`, firmada con HMAC-SHA256 (`doppler_session`).
   - Único servicio con credenciales de **Cloudflare R2**. Genera claves de objeto aleatorias bajo `R2_PREFIX` (`{prefix}{session_id}/{job_id}.wav`), URLs `PUT` prefirmadas (TTL 5 min) y URLs `GET` prefirmadas para reproducción privada (TTL 3 min).
   - Persiste sesiones, trabajos, ventanas y eventos de auditoría en **SQLite (modo WAL)** con migraciones versionadas SQLx (`services/api/migrations/0001_init.sql`).
   - Despacha trabajos con concurrencia máxima `1` (`MAX_CONCURRENT_INFERENCE=1`) sobre una cola persistente acotada (`MAX_QUEUE_DEPTH=16`). Al arrancar recupera trabajos en estado `analyzing` interrumpidos y ejecuta un ciclo periódico de limpieza para objetos expirados (> 24 h) restringido al prefijo de Doppler.
   - Puerto de depuración local: `127.0.0.1:18080` (no expuesto al exterior).
3. **Inferencia acústica interna (`inference` — Python 3.12 / FastAPI / PyTorch CPU):**
   - Un único proceso Uvicorn (`--workers 1`) que carga `model.pt` e `inference.json` **una sola vez** al arranque en modo evaluación CPU (`weights_only=True`, `strict=True`, sin AMP, sin descargar pesos ImageNet).
   - Recibe el binario WAV directamente desde la API Rust por la red interna (`POST /infer`) y devuelve scores sigmoide, clases, características del audio, hashes y tiempos de etapa.
   - Puerto de depuración local: `127.0.0.1:18090` (no expuesto al exterior).

## 2. Flujo real de un archivo WAV

1. El navegador prevalida extensión `.wav`, tamaño (`<= 25 MiB`), cabecera `RIFF/WAVE` y duración (`<= 120 s`).
2. El navegador solicita `POST /api/uploads` a Rust; Rust crea el trabajo en SQLite (`uploading`), asigna una clave aleatoria bajo `R2_PREFIX` y emite la URL `PUT` prefirmada con `Content-Type: audio/wav`.
3. El navegador sube directamente a Cloudflare R2 vía `XMLHttpRequest` mostrando progreso real (bytes y velocidad).
4. El navegador invoca `POST /api/jobs/{id}/confirm` (idempotente). Rust verifica existencia y tamaño real mediante `HeadObject` en R2; si el objeto excede `MAX_FILE_BYTES` o pesa 0 bytes, lo elimina de R2 y marca el trabajo como `failed`.
5. Rust transiciona el trabajo a `queued` dentro de una transacción SQLite.
6. El despachador reserva un trabajo (`queued -> analyzing`), descarga el WAV desde R2 con límite estricto de bytes y lo envía a `http://inference:8000/infer`.
7. Python ejecuta el pipeline fiel a `00_preparacion_insumos.ipynb` y `05_resnet18.ipynb`, devolviendo las ventanas clasificadas y tiempos de etapa.
8. Rust persiste ventanas, hashes (`audio_sha256`, `model_sha256`, `contract_sha256`), umbral y tiempos en SQLite (`completed`).
9. El frontend muestra forma de onda real, espectrograma STFT/Mel calculado en el navegador, tabla sincronizada de ventanas y permite reproducir el original mediante `GET /api/jobs/{id}/audio-url` (URL temporal privada) y exportar JSON o CSV.
10. El usuario puede eliminar inmediatamente el objeto de R2 y el registro SQLite (`DELETE /api/jobs/{id}`), o dejar que la retención automática de 24 h los purgue.

## 3. Cómo reemplazar el checkpoint del modelo de forma segura

Los visitantes de la web **no pueden** cargar modelos arbitrarios. El reemplazo del checkpoint es una operación exclusiva del administrador en el host:

1. Verificar que el nuevo archivo `.pt` conserve el formato exportado por `05_resnet18.ipynb` (`state_dict`, `model_kind: "resnet"`, `params.dropout`, `normalization_mean`, `normalization_std`, `threshold`, `input_shape: [64, 94]`, `class_map`) y que su `inference.json` acompañante coincida exactamente en umbral y estadísticas.
2. Registrar los nuevos hashes SHA-256 en `docs/model-contract.md`.
3. Actualizar `MODEL_PATH` e `INFERENCE_CONFIG_PATH` en `.env` (o reemplazar el archivo montado en solo lectura en `docker-compose.yml`).
4. Reiniciar el servicio de inferencia: `docker compose restart inference`.
5. Comprobar en `curl -s http://localhost:4321/api/health` que `inference.ready` es `true` y que `model_sha256` y `threshold` coinciden con el nuevo artefacto.
6. Reejecutar las pruebas de paridad independiente antes de considerar válido el reemplazo.
