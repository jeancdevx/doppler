# Guía de Monitoreo, Drift, Retroalimentación y Actualización del Modelo

Esta guía documenta la operación y el mantenimiento de Doppler correspondientes al **Capítulo 10 (Monitoreo y Mantenimiento)** en su entorno reproducible de validación local (Linux Manjaro + Docker Compose + Cloudflare R2 privado), así como la lista de verificación para despliegue productivo en Dokploy.

---

## 1. Monitoreo operativo y salud de dependencias (10.1)

### Endpoints de salud y readiness

- **`GET /api/health` (HTTP 200):** mantiene compatibilidad con clientes existentes (`status: "ok" | "degraded"`) y añade `overall_status` (`healthy | degraded | unavailable | unknown`), `ready`, `maintenance_mode`, `components.{api,sqlite,inference,r2}` con latencia efectiva y detalle.
- **`GET /api/ready` (HTTP 200 / 503):** comprobación estricta para balanceadores, monitores externos y automatizaciones. Devuelve **HTTP 503** cuando falla SQLite (`SELECT 1`), inferencia (`/ready`), Cloudflare R2 (`HeadBucket`), o cuando el modo mantenimiento está activado.

### Sonda periódica, incidentes y telemetría desacoplada

- Un worker en `services/api/src/worker/mod.rs` ejecuta sondas reales cada `HEALTH_CHECK_INTERVAL_SECONDS` (por defecto `60 s`) y guarda muestras en `health_samples`.
- Si un componente falla `INCIDENT_FAILURE_THRESHOLD` veces consecutivas (por defecto `3`), se abre automáticamente un incidente en `operational_incidents`; al recuperarse el componente, el incidente se cierra automáticamente con `resolved_at`.
- Los resultados operativos y observacionales por archivo se persisten en `job_telemetry_history` (clave `UNIQUE(job_id)` para evitar duplicados). Esta tabla **sobrevive a la purga de 24 horas** y al borrado voluntario del usuario en el Estudio, conservándose durante `HISTORY_RETENTION_DAYS` (`30` días).
- La medición `persist_ms` se registra **después de `tx.commit()`** efectivo en SQLite.
- El tamaño de almacenamiento se mide en SQLite (`doppler.db` + `-wal` + `-shm`) y en Cloudflare R2 exclusivamente bajo `R2_PREFIX`. Cada ciclo de limpieza deja constancia en `retention_runs`.

### Consola administrativa `/mantenimiento`

- Accesible en `http://localhost:4321/mantenimiento`.
- Protegida por el encabezado `X-Admin-Token` validado en tiempo constante contra `ADMIN_API_TOKEN` del servidor.
- El token reside **únicamente en memoria** en el navegador (nunca en `localStorage`, `sessionStorage`, cookies ni URL) y se elimina al pulsar **Salir**.

---

## 2. Detección de drift de entrada y salida (10.1)

### Unidad de observación y variables

Para evitar la dependencia estadística entre ventanas solapadas (3,0 s con salto 1,5 s), el motor evalúa el drift a nivel de **archivo WAV**:

- **Drift de entrada (audio y representación):** duración, frecuencia de muestreo original, número de canales, pico previo a normalización, RMS previo a normalización, proporción de silencio, proporción de clipping, media y desviación estándar de Log-Mel (`64×94`) y centroide espectral (`obs_v1`, calculado en `services/inference` sin alterar los tensores enviados a ResNet18).
- **Drift de salida (predicciones):** media y máximo de scores sigmoides por archivo y proporción de ventanas clasificadas como `EMERGENCY`.

### Cómo construir e importar una referencia real congelada

> **Estado actual:** En el repositorio local no existe el corpus real de entrenamiento/validación. Los experimentos en `scripts/drift_engine.py` emplean una referencia sintética etiquetada explícitamente como `synthetic_demo` para validar el motor y los 5 estados (`no_alert`, `drift_detected`, `insufficient_data`, `no_reference`, `evaluation_error`).

Para crear una referencia real representativa en un entorno que disponga del corpus de `doppler-ml`:

1. Ejecutar la extracción observacional `obs_v1` + inferencia con el checkpoint congelado (`model.pt`) sobre el conjunto de validación/prueba real manteniendo la agrupación por fuente (`source_group_count`).
2. Calibrar umbrales de Wasserstein 1D normalizada (p. ej. bootstrap p99 con margen) y congelar el JSON con `representative_status: "representative_real_corpus"`, `model_sha256`, `contract_sha256` y `extraction_version: "obs_v1"`.
3. Importarlo vía `POST /api/admin/drift/reference` (con `X-Admin-Token`). Las referencias congeladas **no se eliminan** durante la purga de 30 días.

---

## 3. Actualización periódica, validación y restauración del modelo (10.2)

### Estructura de paquetes versionados (`models/`)

`docker-compose.yml` monta `${ACTIVE_MODEL_DIR:-./models/active}:/models:ro` manteniendo intocada la carpeta original `Doppler_Espectro_Brand_Kit/`.

Cada paquete en `models/packages/<version>/` contiene:
- `model.pt`
- `inference.json`
- `manifest.json` (versión, SHA-256 de ambos archivos, versión de contrato, umbral esperado y metadatos de procedencia)

### Procedimiento controlado (`scripts/model_manager.py`)

```bash
# 1. Inicializar paquete base y directorio activo desde el artefacto original (solo copia)
python3 scripts/model_manager.py init-active

# 2. Validar un paquete offline sin red (SHA-256, contrato, carga estricta CPU e inferencia de prueba)
python3 scripts/model_manager.py validate models/packages/v1.0.0-resnet18-baseline

# 3. Activar con modo mantenimiento, drenado de cola, respaldo, reinicio y rollback automático
python3 scripts/model_manager.py activate models/packages/v1.0.0-resnet18-baseline --reason "Actualización controlada"

# 4. Ejecutar ensayo completo de validación + rechazo de copias inválidas + rollback automático
python3 scripts/model_manager.py drill
```

### Política de revisión periódica propuesta

| Cadencia | Responsable / Herramienta | Qué revisar | Criterio de acción |
| --- | --- | --- | --- |
| **Operativa (diaria)** | `/mantenimiento` → Operación y salud | `/api/ready`, incidentes abiertos, cola, errores internos, retención R2 | Atender cualquier incidente abierto o error de purga R2 |
| **Semanal** | `/mantenimiento` → Drift y Retroalimentación | Alertas de drift entrada/salida; reportes `false_alarm` / `missed_emergency` | Revisar audio antes de 24 h; clasificar casos confirmados o `insufficient_evidence` |
| **Mensual / Candidato** | Evaluación offline fuera del servicio | Tendencia sostenida de drift + volumen de discrepancias confirmadas | Solo reentrenar offline y promover tras paridad, métricas reales y `model_manager.py validate` |

> **Invariante:** Ningún reporte de usuario ni alerta de drift dispara reentrenamiento automático ni altera `model.pt` o el umbral `0.6547843813896179` sin validación humana offline.

---

## 4. Canal de retroalimentación del usuario (10.3)

- **Captura (`FeedbackPanel.svelte`):** disponible en el Estudio para trabajos completados. Admite `false_alarm` y `missed_emergency` (asociados obligatoriamente a una ventana temporal específica) y `technical_issue` / `uncertain_or_other` (generales u opcionalmente ligados a ventana).
- **Seguridad y aislamiento:** exige cookie de sesión HMAC propietaria del trabajo (sesión ajena recibe HTTP `404`), limita comentarios a 1000 caracteres y aplica cuota de `RATE_LIMIT_FEEDBACK_PER_HOUR` (`30/h`).
- **Máquina de estados estricta:** `received → in_review → confirmed | dismissed | insufficient_evidence → resolved`. Los saltos inválidos devuelven HTTP `409` y toda transición se audita en `feedback_events`.
- **Expiración de audio a las 24 h:** el panel indica `audio_currently_available`. Si el WAV ya expiró o fue borrado por el usuario, el revisor debe cerrar con `insufficient_evidence` salvo evidencia previa verificada.
- **Métricas deduplicadas:** se deduplican por `(job_id, window_index, model_sha256)`, excluyen `UNCERTAIN` y comentarios generales, muestran **`No disponibles`** si hay 0 etiquetas verificadas y advierten siempre que la retroalimentación voluntaria constituye una **muestra sesgada**.

---

## 5. Lista de verificación para publicación productiva en Dokploy

Para desplegar Doppler en un VPS gestionado con Dokploy (fuera del alcance de la validación local actual):

1. **Repositorio Git:** URL accesible del repositorio y rama objetivo (`main` o `develop`) conectada en Dokploy.
2. **Dominio HTTPS:** subdominio (p. ej. `doppler.eddux.dev`) con registro DNS `A` apuntando a la IP del VPS para que Traefik emita el certificado TLS.
3. **Compose productivo (`docker-compose.prod.yml`):** retirar los mapeos `127.0.0.1:4321`, `127.0.0.1:18080` y `127.0.0.1:18090`, exponer únicamente `web:4321` hacia la red de Traefik de Dokploy y mantener `api` e `inference` en la red privada interna.
4. **Variables de entorno en Dokploy:** `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PREFIX`, `APP_ORIGIN=https://<tu-dominio>`, `SESSION_HMAC_SECRET` (64 hex aleatorios), `ADMIN_API_TOKEN` (64 hex aleatorios) y límites operativos.
5. **CORS en Cloudflare R2:** añadir el origen productivo exacto `https://<tu-dominio>` en el panel de Cloudflare R2 (manteniendo el bucket privado).
6. **Provisión del modelo (`model.pt` + `inference.json`, ~43 MiB):** al estar excluidos de Git, subir `models/active/` por `scp`/`rsync` a una ruta persistente del host (p. ej. `/opt/doppler/models/active:/models:ro`) o hidratarlo desde un prefijo privado en R2 durante el arranque, manteniendo verificación SHA-256.
7. **Capacidad del VPS y respaldos:** confirmar al menos 2–4 GB de RAM (con margen/swap para picos de 120 s en CPU) y respaldo periódico del volumen SQLite `/data/doppler.db`.
