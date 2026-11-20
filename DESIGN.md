# DESIGN.md — Sistema de Diseño Doppler / Espectro (v3.0 Instrumento Acústico)

Este documento define el sistema visual, tipográfico, de movimiento, accesibilidad y arquitectura de componentes para **Doppler**. Sintetiza el manual oficial `Doppler_Espectro_Brand_Kit` junto con las skills locales del proyecto (`landing-page-design`, `apple-design`, `animate`, `choreograph`, `gestures`, `mobile-native`, `break-ui`, `shadcn-svelte` y `accessibility`).

> **Regla de precedencia:** Cuando una regla genérica de una skill entre en conflicto con un requisito explícito del usuario o con la identidad oficial de **Doppler / Espectro**, prevalecen el usuario y la identidad Doppler / Espectro (por ejemplo: tipografía IBM Plex Sans + IBM Plex Mono alojada localmente, paleta azul/marfil/tinta/estudio oscuro y prohibición de inventar métricas o clasificaciones globales).

---

## 1. Identidad, voz y postura editorial

- **Nombre visible:** Doppler. Logotipo: `doppler` (minúsculas). Dirección visual: **Espectro**.
- **Frase principal:** «Del ruido a la señal.»
- **Descripción funcional:** Detección acústica de sirenas por ventanas temporales de 3,0 s con ResNet18 sobre representaciones Log-Mel.
- **Voz:** Técnica, serena, transparente y verificable.
  - Prohibido usar relleno promocional («revoluciona», «potencia», «sin esfuerzo», «de última generación»).
  - Mensajes del sistema específicos y calmados, sin signos de exclamación ni interjecciones.
  - **Sin guiones dentro de oraciones** en titulares, subtítulos ni cuerpo narrativo; usa puntos o reescribe la frase.
  - **Sin cursivas (`italic`)** ni pesos ultra gruesos (`800`/`900`). Máximo `600` (semibold).
  - **Sin palabras huérfanas:** aplicar `text-wrap: balance` en encabezados y `text-wrap: pretty` en cuerpo.
- **Integridad científica obligatoria:**
  - Preferir «Sirena detectada en esta ventana» y «Sin detección en esta ventana».
  - El `score` nunca se muestra como porcentaje de confianza ni probabilidad calibrada.
  - Nunca se presenta una textura decorativa como espectrograma calculado. El espectrograma del estudio se calcula en tiempo real desde la STFT del audio cargado.
  - Diferenciar explícitamente: ventanas positivas (solapadas cada 1,5 s) vs. cobertura temporal unida, duración del archivo, duración de ventana (3,0 s), tiempo de cola y tiempo de inferencia.
  - Nunca emitir una «clasificación global validada» del archivo.

---

## 2. Paleta de color y tokens semánticos (WCAG 2.2 AA)

Todos los colores se mapean a tokens semánticos CSS y variables `@theme inline` de Tailwind v4. Nunca se usan valores hexadecimales arbitrarios ni anulaciones `dark:` manuales dentro de componentes.

### Paleta maestra Doppler / Espectro

| Token | Hex | Rol |
| --- | --- | --- |
| `--doppler-blue-600` | `#3156D3` | Acción primaria sobre superficies claras, acento de marca |
| `--doppler-blue-700` | `#2643A8` | Hover de acción primaria en tema claro |
| `--doppler-blue-500` | `#5275EF` | Anillo de foco visible (`:focus-visible`) |
| `--doppler-blue-300` | `#9BB1FF` | Acción primaria, controles activos y trazos de señal sobre fondo oscuro (`#090F1D` / `#101B30`) |
| `--doppler-neutral-50` | `#F5F3EC` | Fondo editorial principal (marfil) y texto primario en estudio oscuro |
| `--doppler-neutral-100` | `#EAE8E1` | Superficie secundaria clara y bandas editoriales |
| `--doppler-neutral-0` | `#FFFFFF` | Superficie elevada clara (tarjetas, paneles en tema claro) |
| `--doppler-neutral-200` | `#D7D9DF` | Bordes en tema claro |
| `--doppler-neutral-600` | `#52617B` | Texto secundario en tema claro (contraste ≥ 5,5:1 sobre `#F5F3EC`) |
| `--doppler-neutral-800` | `#172B4D` | Tinta principal en tema claro y superficie elevada en tema oscuro |
| `--doppler-neutral-900` | `#101B30` | Panel del estudio en tema oscuro |
| `--doppler-neutral-950` | `#090F1D` | Fondo base del estudio oscuro (nunca negro puro para preservar profundidad espectral) |
| `--doppler-neutral-300` | `#BDC4D1` | Texto secundario en tema oscuro (contraste ≥ 9:1 sobre `#090F1D`) |
| `--doppler-neutral-700` | `#34435C` | Bordes y retícula técnica en tema oscuro |

### Semántica de estados (siempre acompañada de texto e icono, nunca solo color)

| Estado | Tema oscuro (texto / fondo / borde) | Tema claro (texto / fondo / borde) |
| --- | --- | --- |
| Ventana objetivo (`EMERGENCY`) | `#FFDF9F` / `#2D2414` / `#F0C779` | `#744A00` / `#FEF4DF` / `#D8A84E` |
| Completado / Listo | `#B6EFDA` / `#142E28` / `#355B50` | `#145334` / `#E3F5EA` / `#9CCFB4` |
| Error / Validación fallida | `#FFCDCD` / `#33181D` / `#8C4148` | `#8F1D24` / `#FDECEC` / `#E3A0A5` |
| En cola / Analizando | `#BECDFF` / `#152447` / `#3A5499` | `#233B88` / `#EEF2FF` / `#BECDFF` |

**Restricciones de contraste verificadas:**
- Nunca usar `#3156D3` para texto pequeño sobre `#090F1D`: usar `#9BB1FF`.
- Nunca colocar texto blanco sobre `#9BB1FF`: usar `#090F1D` (`--doppler-onAction`).
- Contraste mínimo: `4.5:1` texto normal, `3:1` texto grande y elementos gráficos/foco.
- Fondos de sección planos (sin gradientes decorativos de fondo); el degradado lineal queda reservado exclusivamente para acentos tipográficos del titular hero o la envolvente de señal.
- Nunca aplicar borde a un solo lado de una tarjeta (los bordes rodean los 4 lados o no se usan; solo se permite línea divisoria estructural `Separator` entre regiones).

---

## 3. Tipografía (alojada localmente, sin fuentes externas)

- **Primaria:** `IBM Plex Sans` (`400`, `500`, `600`) servida desde `/fonts/woff2/` (`IBMPlexSans-{400,500,600}.woff2`).
- **Datos y códigos:** `IBM Plex Mono` (`400`) servida desde `/fonts/woff2/IBMPlexMono-Regular.woff2`, exclusivamente para tiempos (`00:03.0`), scores (`0.6548`), hashes SHA-256, frecuencias y etiquetas técnicas. Siempre con `font-variant-numeric: tabular-nums` para evitar saltos horizontales al reproducir audio.

### Escala tipográfica nombrada (mapeada a escala Tailwind)

| Clase utilitaria | Escala Tailwind | Peso | Tracking / Interlineado | Uso |
| --- | --- | --- | --- | --- |
| `.heading-1` | `text-5xl md:text-6xl` | `500` | `-0.04em` / `1.0` | Titular Hero |
| `.heading-2` | `text-3xl md:text-5xl` | `500` | `-0.035em` / `1.08` | Encabezado de sección y Tagline Reveal |
| `.heading-3` | `text-2xl md:text-4xl` | `500` | `-0.03em` / `1.12` | Subsecciones editoriales |
| `.heading-4` | `text-xl md:text-2xl` | `600` | `-0.02em` / `1.2` | Título de archivo y paneles del estudio |
| `.title-3` | `text-base` | `500` | `-0.01em` / `1.5` | Títulos de tarjeta y pasos |
| `.body-3` | `text-base` | `400` | `0` / `1.5` | Cuerpo principal (mínimo 16 px en aplicación) |
| `.body-6` | `text-sm` | `400` | `0` / `1.43` | Descripción secundaria y notas |
| `.button-md` | `text-base` | `500` | `-0.01em` / `1.5` | Acción principal |
| `.button-sm` | `text-sm` | `500` | `0` / `1.43` | Controles de barra y botones secundarios |
| `.caption-4` | `text-xs` | `500` | `0.06em` / `1.33` | Etiquetas mono, timestamps, metadatos |

---

## 4. Espaciado, radios y retícula

- **Escala de espaciado estricta:** `0`, `2px`, `4px`, `8px`, `12px`, `16px`, `24px`, `32px`, `40px`, `48px`, `64px`, `80px`, `96px`.
- **Contenedor máximo:** `1440px` (`max-w-[1440px]`), retícula de 12 columnas en escritorio y 4 en móvil (`390px` validado sin desbordamiento horizontal).
- **Fórmula de radios anidados (`inner = outer - gap` cuando `gap < 32px` y resultado `> 2px`):**
  - Contenedor del estudio: `rounded-2xl` (`16px`)
  - Paneles internos con padding `8px`: `rounded-lg` (`8px`)
  - Controles, botones e inputs: `rounded-lg` (`8px`)
  - Chips y etiquetas de estado: `rounded-full`
- **Jerarquía espacial del estudio:** El área de visualización de señal (forma de onda + espectrograma calculado + transporte + tabla sincronizada de ventanas) ocupa ≥ 72 % del ancho en escritorio, con una barra lateral compacta de sesión y acciones.

---

## 5. Estrategia multi-catálogo de componentes (sin reinventar primitivas)

El frontend en **Astro 5 + Svelte 5 (runes) + Tailwind CSS v4** integra múltiples catálogos personalizables y bibliotecas auditadas, evitando escribir primitivas accesibles desde cero:

| Catálogo / Origen | Componentes adoptados y adaptados a Espectro | Ubicación |
| --- | --- | --- |
| **shadcn-svelte + Bits UI** | `Button`, `Badge`, `Card`, `Tabs` (lista de vistas Forma de onda / Espectro / Ventanas), `Dialog` / `AlertDialog` (confirmación de borrado en R2 y SQLite), `Tooltip`, `Progress`, `Separator`, `Skeleton`, `ScrollArea`, `Accordion` (FAQ técnica) | `apps/web/src/components/ui/` |
| **Sonner (`svelte-sonner`)** | Notificaciones no bloqueantes de subida, exportación, copiado y errores recuperables | `apps/web/src/components/ui/sonner/` |
| **Untitled UI (patrón File Upload & Metric Cards)** | Zona de arrastre WAV con prevalidación local, tarjeta de archivo en progreso con tasa de transferencia real (bytes/s, porcentaje XHR a R2) y tarjetas de métricas tabulares sin jitter | `apps/web/src/components/AudioDropzone/`, `apps/web/src/components/MetricGrid/` |
| **ReUI (patrón Pipeline Stepper & Data Status)** | Indicador horizontal de etapas del pipeline (`validando → cargando → en cola → analizando → completado`) con duración real por etapa y badges de estado con punto indicador | `apps/web/src/components/PipelineStepper/` |
| **Aceternity UI (patrón Spectral Bento & Spotlight Surface)** | Superficie de retícula espectral interactiva en la entrada y tarjetas bento de arquitectura/contrato con realce sutil de borde al puntero (activado solo bajo `(hover: hover) and (pointer: fine)` y desactivado con `prefers-reduced-motion`) | `apps/web/src/components/SpectralHero/`, `apps/web/src/components/BentoFeatureGrid/` |
| **Iconografía (`phosphor-svelte` + iconos del kit)** | Iconos de trazo uniforme Phosphor (según B6 de `landing-page-design`) + logos SVG maestros de `Doppler_Espectro_Brand_Kit/logos/svg/` | `apps/web/public/logos/`, `phosphor-svelte` |

---

## 6. Arquitectura de página y flujo de conversión (Landing + Recorrido Scroll + Estudio Real)

1. **Barra flotante obsidiana translúcida (`backdrop-filter: blur(12px)`):** Marca `doppler` en versión invertida (`doppler-horizontal-reverse.svg`), enlaces semánticos (`Recorrido`, `Estudio`, `Arquitectura`, `Preguntas`) y acción única «Abrir estudio». En móvil abre panel de altura completa en obsidiana con cierre por `Escape` y restauración de foco. Incluye enlace «Saltar al contenido principal».
2. **Acto 1 — Hero de campo acústico interactivo (`SpectralHero` + `HeroAcousticCanvas`):**
   - Portada full-bleed en obsidiana (`#090F1D`) con campo acústico tridimensional de 26 cintas espectrales en canvas HiDPI interactivo al puntero (estático bajo `prefers-reduced-motion`).
   - Titular sobredimensionado `.heading-display` «Del ruido a la señal.» con acento espectral, CTA único con **Magic UI Border Beam** («Cargar archivo WAV»), tarjeta de contrato congelado (`16 000 Hz`, `3,0 s / 1,5 s`, `Log-Mel 64×94`, `θ 0,6548`) y regla acústica calibrada estilo Teenage Engineering en la base.
3. **Acto 2 — Recorrido continuo guiado por scroll (`ScrollAcousticStory`, 4 capítulos):**
   - Escenario sticky `100dvh` sin cortes que transforma continuamente una onda acústica al hacer scroll: (1) Armonización `16 kHz / peak 0,99`, (2) Ventanas solapadas `3,0 s / salto 1,5 s`, (3) Paisaje topográfico Log-Mel `64 × 94`, (4) Decisión ResNet18 CPU frente al umbral `0,6548`.
   - Riel lateral interactivo de capítulos y degradación limpia en móvil y `prefers-reduced-motion`.
4. **Acto 3 — Estudio interactivo real (`AudioStudio`, isla Svelte 5 sobre lienzo marfil con mesa oscura):**
   - **Sin datos ilustrativos falsos en el flujo normal.** Estado vacío compuesto con zona de arrastre/selección WAV, explicación explícita de límites (25 MiB, 120 s, ≥ 3,0 s) y política de retención 24 h en Cloudflare R2 privado.
   - **Progreso real a R2:** `XMLHttpRequest` `PUT` directo a la URL prefirmada con barra de progreso, bytes subidos y botón de cancelar/reintentar.
   - **Visualización triple sincronizada:**
     - **Forma de onda** decodificada del WAV (con bandas sombreadas en ámbar para ventanas `EMERGENCY`, marca de ventana seleccionada, cursor de reproducción sincronizado y búsqueda por clic o teclado `ArrowLeft`/`ArrowRight`).
     - **Espectrograma Log-Mel / STFT calculado** en el navegador desde el propio audio decodificado (etiquetado con parámetros reales de FFT y rango de frecuencias; nunca una textura decorativa).
     - **Perfil de scores por ventana (`WindowScoreChart`):** Gráfico interactivo de barras `0.00–1.00` con línea punteada horizontal del umbral congelado (`0.6548`), selección sincronizada con el reproductor y la tabla.
   - **Reproducción autorizada desde R2:** Utiliza la URL GET firmada de corta duración (`/api/jobs/{id}/audio-url`), sin reproducción automática (`autoplay` prohibido).
   - **Inspector de ventanas sincronizado (`WindowTable`):** Lista/tabla navegable con teclado mostrando inicio, fin, score raw (4 decimales), etiqueta (`EMERGENCY` / `NON_EMERGENCY`), delta respecto al umbral (`0.6548`), filtros y resumen claro separando conteo de ventanas positivas de cobertura temporal unida.
   - **Trazabilidad y acciones:** SHA-256 del audio, SHA-256 del modelo, versión de contrato, desglose de latencias por etapa, exportación **JSON** y **CSV**, y eliminación verificada (R2 + SQLite) con `AlertDialog`.
   - **Tema claro/oscuro independiente del estudio** con conmutador accesible y persistencia en `localStorage`.
5. **Acto 4 — Tagline Reveal en contraste obsidiana (`TaglineReveal`):** Declaración editorial full-bleed en `#090F1D` cuyas palabras revelan su luminancia progresivamente al entrar al viewport mediante `IntersectionObserver` (inmediato bajo `prefers-reduced-motion`).
6. **Acto 5 — Bento asimétrico de 12 columnas (`BentoFeatureGrid`):** Tarjeta protagonista de 7 columnas en obsidiana con diagrama SVG animado del flujo real `Navegador → R2 privado → Rust Axum → Python ResNet18` y spotlight radial al puntero; tarjeta blueprint de 5 columnas del contrato `64×94`; fila inferior de 3 módulos de 4 columnas (cola SQLite concurrencia 1, privacidad/TTL 24 h, Docker Compose fijado).
7. **Acto 6 — FAQ técnica (Accordion accesible) + Pie editorial + 404 personalizada.**

---

## 7. Movimiento, gestos y experiencia móvil nativa

- **Curvas oficiales:**
  - `--ease-out: cubic-bezier(0.22, 1, 0.36, 1)` (entradas y transiciones de estado, `140ms`–`220ms` en controles del estudio, `500ms`–`650ms` en revelados editoriales).
  - Nunca `transition: all`, nunca `ease-in` en entradas UI, nunca animar `width`/`height`/`top`/`left` (solo `transform` y `opacity`).
  - **Sin animación en acciones de alta frecuencia / atajos de teclado** (selección de ventana con flechas, pausa/reproducción con `Espacio`).
  - **Sin movimiento decorativo continuo durante la lectura de resultados.**
- **Móvil nativo (`mobile-native`):**
  - `viewport-fit=cover` + `interactive-widget=resizes-content` + `<meta name="theme-color">` para claro y oscuro.
  - `-webkit-tap-highlight-color: transparent`, `touch-action: manipulation` en controles, `user-select: none` solo en botones/controles (nunca en cuerpo ni hashes copiables).
  - Todo `:hover` protegido bajo `@media (hover: hover) and (pointer: fine)`.
  - Feedback táctil inmediato en `:active` (`scale(0.98)` en `100ms`).
  - Inputs con `font-size >= 16px` para evitar zoom forzado en iOS.
  - Objetivos táctiles mínimos `44×44px` en controles primarios (`≥ 24×24px` WCAG 2.2 AA).
- **Accesibilidad (`accessibility` + `break-ui`):**
  - `prefers-reduced-motion: reduce` colapsa desplazamientos a cambios de opacidad o inmediatos.
  - `prefers-reduced-transparency: reduce` y `prefers-contrast: more` aumentan opacidad y contraste de bordes.
  - `min-width: 0` en columnas flex/grid, `flex-shrink: 0` en iconos/badges, truncado central para nombres largos de archivo WAV y `title`/tooltip con nombre completo.
  - Todos los gráficos tienen `role="img"` / controles equivalentes operables por teclado y anuncios en `aria-live="polite"`.

---

## 8. Extensiones de Monitoreo, Retroalimentación y Mantenimiento (Capítulo 10)

- **Panel de retroalimentación en el Estudio (`FeedbackPanel.svelte`):** integrado dentro del chasis `[data-studio-theme]` para análisis completados; sincroniza automáticamente el selector de ventana con la ventana seleccionada en el estudio, advierte explícitamente sobre la expiración del WAV a las 24 h y muestra el historial de reportes de la sesión actual con badges semánticos de estado (`received` → `resolved`).
- **Consola operativa (`/mantenimiento`, `MaintenanceConsole/`):** vista interna dedicada bajo los mismos tokens oscuros de instrumento (`#090F1D`, `#101B30`, `#9BB1FF`, `#F0C779`, `#86D6B8`) con acceso por token en memoria (`X-Admin-Token`), cuatro pestañas modulares (`OperationalPanel`, `DriftPanel`, `FeedbackAdminPanel`, `DeploymentsPanel`), tablas con desplazamiento horizontal seguro (`overflow-x-auto`) sin desbordamiento en 390 px, y banners explícitos de honestidad metodológica (`Referencia representativa pendiente`, `No disponibles` cuando `n=0` etiquetas verificadas).
