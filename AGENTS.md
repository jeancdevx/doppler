# AGENTS.md — Guía de Ingeniería y Convenciones de Doppler

Este documento establece las reglas operativas, arquitectónicas, de calidad y de seguridad para cualquier agente o colaborador que trabaje en este repositorio.

---

## 1. Arquitectura y responsabilidades

Doppler es una aplicación web local reproducible (Docker Compose en Linux Manjaro) conectada a almacenamiento privado real en **Cloudflare R2**:

```text
Navegador ──► Caddy (:4321) ──┬── /         ──► Frontend estático Astro + isla Svelte 5
                              └── /api/*    ──► API Rust (Axum + Tokio + SQLite)
                                                   ├── Cloudflare R2 real (aws-sdk-s3, URLs PUT/GET firmadas)
                                                   └── Servicio interno Python (FastAPI + PyTorch CPU, 1 proceso)
```

| Directorio | Responsabilidad | Stack |
| --- | --- | --- |
| `apps/web` | Sitio editorial y estudio interactivo de audio | Astro 5, TypeScript, Svelte 5 (runes), Tailwind CSS v4, Bits UI / shadcn-svelte, svelte-sonner, Phosphor |
| `services/api` | Sesiones anónimas HMAC, presigned URLs R2, validación, cola persistente SQLite, despachador (concurrencia 1), exportación JSON/CSV, limpieza por retención | Rust (edition 2021), Axum, Tokio, SQLx (SQLite + migraciones), `aws-sdk-s3` |
| `services/inference` | Decodificación WAV, pipeline acústico fiel a `00_preparacion_insumos.ipynb`, inferencia CPU ResNet18 fiel a `05_resnet18.ipynb` | Python 3.12, FastAPI, Pydantic v2, PyTorch CPU, torchvision, librosa, soundfile, soxr |
| `config` | `Caddyfile`, CORS R2, configuración compartida | Caddy 2, JSON |
| `scripts` | Verificación R2, configuración CORS, generación de fixtures sintéticas, benchmarks CPU, generación y empaquetado de evidencias | Python 3, Bash |
| `tests` | Paridad independiente con notebooks, matriz de archivos WAV, integración real R2, E2E y accesibilidad Playwright | pytest, Playwright |
| `docs` | Contrato del modelo, OpenAPI, arquitectura, guía R2, guía de pruebas, evidencias, troubleshooting y validación local | Markdown, OpenAPI 3.1 YAML |
| `evidence` | Ejecuciones reproducibles `evidence/<run_id>/` + manifiestos SHA-256 (nunca incluir secretos, cookies, URLs firmadas ni checkpoints) | JSON, CSV, SVG, PNG, Markdown |
| `Doppler_Espectro_Brand_Kit` | Insumos originales entregados (**solo lectura; nunca modificar ni borrar**) | Brand Kit, `model.pt`, `inference.json`, notebooks |

---

## 2. Convenciones de estructura por lenguaje

### 2.1 Frontend (`apps/web`) — Convención de Josh W. Comeau adaptada a Astro + Svelte

Organización por función en `apps/web/src/` con colocación para componentes complejos y barrel `index.ts`:

```text
apps/web/src/
  components/
    ui/                     # Primitivas de catálogos (shadcn-svelte / Bits UI, sonner)
      button/
      badge/
      card/
      tabs/
      dialog/
      alert-dialog/
      tooltip/
      progress/
      separator/
      skeleton/
      accordion/
      sonner/
    AudioStudio/            # Componente complejo colocado
      AudioStudio.svelte
      AudioStudio.constants.ts
      AudioStudio.helpers.ts
      AudioStudio.types.ts
      index.ts
    AudioDropzone/
    WaveformCanvas/
    SpectrogramCanvas/
    PipelineStepper/
    WindowTable/
    MetricGrid/
    SpectralHero/
    TaglineReveal/
    BentoFeatureGrid/
    Navbar/
    Footer/
  constants/                # Constantes globales (API, límites, contrato)
  helpers/                  # Funciones puras (formato tiempo, WAV precheck, STFT/Mel web, API client)
  hooks/                    # Módulos reactivos Svelte 5 (.svelte.ts: tema, audio player, job polling, reduced motion)
  layouts/                  # Layouts Astro (BaseLayout.astro)
  pages/                    # Rutas Astro (index.astro, 404.astro)
  styles/                   # global.css (tokens Doppler Espectro + Tailwind v4 @theme)
```

Alias obligatorio: `@/*` → `./src/*` (configurado en `tsconfig.json` y respetado por `oxfmt` `internalPattern: ["@/"]`).

### 2.2 Backend Rust (`services/api`) — Convención modular Axum + Apollo Rust Best Practices

```text
services/api/
  Cargo.toml
  Cargo.lock                # Versiones fijadas; conservar siempre
  migrations/               # Migraciones SQLite versionadas (0001_init.sql, ...)
  src/
    main.rs                 # Arranque, carga de configuración, migraciones, servidor y worker
    lib.rs                  # Ensamblado de router para pruebas de integración
    config.rs               # Configuración tipada desde entorno (sin secretos en logs)
    error.rs                # Jerarquía de errores con thiserror y códigos HTTP explícitos
    state.rs                # AppState compartido (Arc<SqlitePool>, R2Client, InferenceClient, Config)
    domain/                 # Modelos de dominio, máquinas de estado válidas, DTOs
    db/                     # Repositorio SQLite modular (mod, models, sessions, jobs, results)
    maintenance/            # Monitoreo y mantenimiento modular (mod, auth, health, telemetry, drift, feedback, deployments)
    storage/                # Cliente Cloudflare R2 (aws-sdk-s3), presigned PUT/GET, HEAD, uso por prefijo
    inference/              # Cliente HTTP interno hacia FastAPI con límites de tamaño y timeout
    routes/                 # Controladores HTTP modulares (mod, auth, health, uploads, jobs, feedback, admin)
    worker/                 # Despachador de cola (concurrencia 1), sonda de salud (60s) y limpieza por retención
```

Reglas Rust obligatorias:
- Prohibido `.unwrap()` / `.expect()` en código de producción (solo en tests).
- Errores con `thiserror`; propagación con `?`.
- Preferir `&str`/`&[T]` sobre `.clone()` innecesarios.
- Verificar con `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` y `cargo test`.

### 2.3 Servicio de inferencia Python (`services/inference`) — Layout `src/` + FastAPI Best Practices

```text
services/inference/
  pyproject.toml
  requirements.lock         # Dependencias exactamente fijadas (==)
  src/
    doppler_inference/
      __init__.py
      config.py             # Settings inmutables (MODEL_PATH, INFERENCE_CONFIG_PATH, límites, hilos)
      schemas.py            # Modelos Pydantic v2 (sin Ellipsis ni RootModel; Annotated para params)
      audio.py              # Decodificación WAV, resample soxr_hq, peak 0.99, ventanas 3s/1.5s, Log-Mel 64×94
      model.py              # VisualTransfer (ResNet18), carga estricta CPU sin ImageNet, inferencia sin AMP
      service.py            # Orquestación de etapas con medición de tiempos y metadatos de trazabilidad
      router.py             # APIRouter (/health, /ready, /infer) usando def sync para cómputo CPU bloqueante
      main.py               # Lifespan FastAPI (carga única del modelo al arranque, max_body_size)
  tests/
```

Reglas Python obligatorias:
- Usar funciones `def` (no `async def`) en endpoints con cómputo CPU síncrono (FastAPI las ejecuta en threadpool sin bloquear el event loop).
- Usar `Annotated` para parámetros y dependencias; declarar tipos de retorno en todas las rutas.
- Formateo y lint con `ruff check` y `ruff format --check`.

---

## 3. Gestor de paquetes, versionado y calidad de código

- **Usar exclusivamente `pnpm`** (prohibido `npm` o `yarn`).
- **Versiones exactas sin carets (`^`) ni tildes (`~`)**: instalar siempre con `pnpm add -E` / `pnpm add -D -E`. Conservar `pnpm-lock.yaml`, `Cargo.lock` y `requirements.lock`.
- **Evitar etiquetas flotantes `latest`** en Dockerfiles y `docker-compose.yml`; fijar versiones estables explícitas de imágenes base.
- **Linter y formateador JS/TS/Astro:** `oxlint` (`.oxlintrc.json`) y `oxfmt` (`.oxfmtrc.json`) configurados en raíz / `apps/web` siguiendo exactamente la configuración del proyecto.
- **Git Hooks y Commits:**
  - `husky` + `lint-staged` en `pre-commit` (ejecuta `oxfmt --check` / `oxlint` sobre archivos modificados).
  - `commitlint` (`@commitlint/config-conventional`) en `commit-msg` exigiendo **Conventional Commits** (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`, `ci:`, `build:`).

---

## 4. Fidelidad del modelo (invariantes no negociables)

Antes de modificar cualquier parte del pipeline de inferencia, consultar `docs/model-contract.md`:
1. Nunca descargar pesos ImageNet en arranque (`resnet18(weights=None)` + `load_state_dict(..., strict=True)`).
2. Nunca redimensionar Log-Mel a `224×224`, ni aplicar normalización ImageNet, ni recalcular media/desviación con el audio del usuario.
3. Nunca reajustar el umbral `0.6547843813896179` ni agregar reglas heurísticas de silencio que anulen al clasificador.
4. Nunca rellenar silenciosamente archivos menores de 3,0 s ni la cola incompleta final.
5. Las pruebas de paridad deben comparar el servicio contra una implementación de referencia independiente extraída de las notebooks `00_preparacion_insumos.ipynb` y `05_resnet18.ipynb`.

---

## 5. Seguridad, R2 y manejo de secretos

- Las credenciales de Cloudflare R2 residen únicamente en `.env` (excluido de Git y Docker build context) y se consumen exclusivamente desde `services/api` (Rust). Nunca se pasan a Python ni al frontend.
- Prohibido imprimir `.env`, claves, cookies de sesión, tokens o URLs firmadas completas en consola, logs, respuestas de error o `evidence/`.
- Las operaciones de limpieza y prueba se limitan estrictamente a `R2_PREFIX` y `R2_TEST_PREFIX`. Nunca modificar ni borrar objetos ajenos ni habilitar acceso público al bucket.
- El cliente jamás elige claves de objeto arbitrarias ni suministra URLs externas para inferencia.
- Verificar tamaño real del objeto en R2 (`HeadObject`) antes de encolar y volver a acotar la descarga al leer el cuerpo.

---

## 6. Skills locales aplicables

Antes de diseñar o modificar componentes UI, consultar `DESIGN.md` y las skills en `.agents/skills/`:
- Diseño y layout: `landing-page-design`, `apple-design`, `shadcn-svelte`, `accessibility`, `mobile-native`, `break-ui`.
- Movimiento: `animate`, `choreograph`, `gestures`, `animation-performance`, `review-animations`, `ask-sonner`.
- Stack: `astro`, `svelte-core-bestpractices`, `rust-best-practices`, `fastapi`.
