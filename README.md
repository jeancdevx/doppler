# Doppler — Detección Acústica de Sirenas por Ventanas Temporales

Aplicación web funcional de validación local (Linux Manjaro + Docker Compose) con almacenamiento privado real en **Cloudflare R2** e inferencia CPU fiel al modelo académico **ResNet18 sobre representaciones Log-Mel (`05_resnet18`)**.

> **Alcance de esta entrega:** Ejecución y validación local reproducible con almacenamiento real en Cloudflare R2 privado. Los resultados de latencia y memoria medidos corresponden a validación local y no a un servidor de producción.

---

## Arquitectura

| Componente | Tecnología | Puerto local (loopback) | Responsabilidad |
| --- | --- | --- | --- |
| Entrada y estáticos (`web`) | **Caddy 2.9.1** + **Astro 5** + **Svelte 5** + **Tailwind CSS v4** | `http://localhost:4321` | Sirve el frontend compilado, fuentes IBM Plex locales y proxy `/api/*` → Rust |
| API principal (`api`) | **Rust 1.94** + **Axum 0.8** + **Tokio** + **SQLite (WAL)** + **`aws-sdk-s3`** | `127.0.0.1:18080` *(depuración)* | Sesiones HMAC, URLs `PUT`/`GET` firmadas R2, validación de tamaño real, cola persistente (concurrencia 1), exportación JSON/CSV y limpieza 24 h |
| Inferencia interna (`inference`) | **Python 3.12** + **FastAPI** + **PyTorch 2.11.0 CPU** + **librosa / soxr** | `127.0.0.1:18090` *(depuración)* | Un solo proceso; carga `model.pt` una sola vez sin pesos ImageNet; ejecuta preparación acústica e inferencia CPU sin AMP |
| Almacenamiento remoto | **Cloudflare R2 privado** (API S3) | Externo HTTPS | Almacena WAV originales bajo prefijo exclusivo `R2_PREFIX`; credenciales aisladas en Rust |

---

## Requisitos en Linux Manjaro

- Docker Engine (`docker`) y Docker Compose v2 (`docker compose`)
- `pnpm` 10.x (gestor exclusivo para el workspace frontend; **no usar `npm`**)
- Node.js `>= 22.23.4` (para desarrollo local, `oxlint`, `oxfmt` y Playwright)
- Python 3.10+ (para scripts de verificación R2, integración y generación de evidencias)
- Un bucket privado de Cloudflare R2 y credenciales S3 API en `.env`

---

## Instalación y arranque rápido

### 1. Configurar entorno (`.env`)

```bash
cp .env.example .env
```

Edita `.env` (excluido de Git y Docker) con tus credenciales reales de Cloudflare R2 (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`) y genera un `SESSION_HMAC_SECRET` aleatorio de 64 caracteres hexadecimales:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Verificar acceso real y CORS en Cloudflare R2

```bash
python3 scripts/r2_check.py --ensure-cors
```

Si el token de R2 tiene permisos de mínimo privilegio (`Object Read & Write`), `PutBucketCors` devolverá HTTP 403; en ese caso aplica el bloque JSON de [config/r2-cors.json](config/r2-cors.json) en **Cloudflare Dashboard → R2 → tu bucket → Settings → CORS Policy** sin alterar reglas ajenas. Ver [docs/r2-setup.md](docs/r2-setup.md).

### 3. Arrancar la aplicación completa con Docker Compose

```bash
docker compose up -d --build
```

Comprueba salud del conjunto y disponibilidad del modelo:

```bash
docker compose ps
curl -s http://localhost:4321/api/health | python3 -m json.tool
```

Abre la aplicación en: **`http://localhost:4321`**

### 4. Detener servicios

```bash
docker compose down
```

*(Para borrar también el volumen local SQLite: `docker compose down -v`.)*

---

## Comandos de calidad, pruebas y evidencias

```bash
# Instalar dependencias JS con versiones exactas bloqueadas (solo pnpm)
pnpm install --frozen-lockfile

# Comprobaciones frontend (Astro, Svelte, formato oxfmt y lint oxlint)
pnpm run check:web
pnpm run format:check
pnpm run lint

# Paridad independiente con notebooks y matriz de archivos WAV (offline, sin red)
docker run --rm --network none \
  -v "$(pwd)/Doppler_Espectro_Brand_Kit/model:/models:ro" \
  doppler-inference:1.0.0 \
  sh -c "ruff check --no-cache src tests && pytest -v -o cache_dir=/tmp/pytest_cache tests/test_parity_and_files.py"

# Pruebas de integración real (Caddy + Rust + R2 real + Python + SQLite + reinicio)
python3 tests/integration/test_api_and_r2.py

# Pruebas de interfaz, móvil 390 px, teclado, tema claro/oscuro y reduced motion
pnpm run test:e2e

# Generar paquete completo de evidencias reproducibles (benchmark n=30, memoria, diagramas SVG/PNG, capturas)
pnpm run evidence:generate

# Empaquetar la última evidencia en ZIP con manifiesto SHA-256 y auditoría antisecretos
pnpm run evidence:pack
```

---

## Documentación técnica

- [docs/model-contract.md](docs/model-contract.md) — Contrato congelado del modelo `05_resnet18`, hashes y preparación acústica.
- [docs/openapi.yaml](docs/openapi.yaml) — Especificación OpenAPI 3.1.0 de todos los endpoints HTTP.
- [docs/architecture.md](docs/architecture.md) — Arquitectura, flujo real de datos y procedimiento seguro para reemplazar checkpoints.
- [docs/r2-setup.md](docs/r2-setup.md) — Configuración privada de Cloudflare R2, CORS exacto y retención de 24 h.
- [docs/testing.md](docs/testing.md) — Protocolo de pruebas (paridad, archivos, R2, integración e interfaz).
- [docs/evidence.md](docs/evidence.md) — Generación y empaquetado de evidencias académicas para 9.1, 9.2 y 9.3.
- [docs/troubleshooting.md](docs/troubleshooting.md) — Solución de errores frecuentes.
- [DESIGN.md](DESIGN.md) y [AGENTS.md](AGENTS.md) — Sistema de diseño Doppler/Espectro y convenciones del repositorio.
