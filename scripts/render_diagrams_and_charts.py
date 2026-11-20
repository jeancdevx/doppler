#!/usr/bin/env python3
"""Genera diagramas de arquitectura/secuencia y gráficas de validación local en SVG (y PNG vía Playwright).

Todos los rótulos, títulos, ejes y notas de procedencia están en español
con la paleta oficial Doppler / Espectro.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from pathlib import Path


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def svg_components_diagram() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1120 620" width="1120" height="620" font-family="IBM Plex Sans, sans-serif">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#3156D3"/>
    </marker>
    <marker id="arrowDark" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#172B4D"/>
    </marker>
  </defs>
  <rect width="1120" height="620" fill="#F5F3EC"/>
  <text x="40" y="38" font-size="22" font-weight="600" fill="#172B4D">Arquitectura de componentes — Doppler (validación local)</text>
  <text x="40" y="60" font-size="13" fill="#52617B">Docker Compose en Linux Manjaro con almacenamiento privado real en Cloudflare R2</text>

  <!-- Navegador -->
  <rect x="40" y="130" width="210" height="170" rx="14" fill="#FFFFFF" stroke="#172B4D" stroke-width="2"/>
  <text x="60" y="162" font-size="11" font-family="IBM Plex Mono, monospace" fill="#3156D3">CLIENTE WEB</text>
  <text x="60" y="186" font-size="16" font-weight="600" fill="#172B4D">Navegador</text>
  <text x="60" y="212" font-size="12" fill="#52617B">Astro 5 + Isla Svelte 5</text>
  <text x="60" y="232" font-size="12" fill="#52617B">Prevalidación WAV local</text>
  <text x="60" y="252" font-size="12" fill="#52617B">Onda y espectro reales</text>
  <text x="60" y="272" font-size="12" fill="#52617B">PUT/GET directo a R2</text>

  <!-- Contenedor Docker Compose -->
  <rect x="305" y="114" width="525" height="456" rx="18" fill="#EAE8E1" stroke="#34435C" stroke-dasharray="6 4" stroke-width="1.5"/>
  <text x="325" y="136" font-size="11" font-family="IBM Plex Mono, monospace" fill="#172B4D">RED INTERNA DOCKER COMPOSE (PUERTOS SOLO EN 127.0.0.1)</text>

  <!-- Caddy -->
  <rect x="330" y="148" width="210" height="125" rx="12" fill="#090F1D" stroke="#34435C" stroke-width="1.5"/>
  <text x="348" y="175" font-size="10" font-family="IBM Plex Mono, monospace" fill="#9BB1FF">ENTRADA · :4321</text>
  <text x="348" y="198" font-size="16" font-weight="600" fill="#F5F3EC">Caddy 2.9.1</text>
  <text x="348" y="222" font-size="12" fill="#BDC4D1">Sirve / (Astro estático)</text>
  <text x="348" y="242" font-size="12" fill="#BDC4D1">Proxy /api/* → Rust API</text>

  <!-- Rust API -->
  <rect x="575" y="148" width="230" height="185" rx="12" fill="#101B30" stroke="#9BB1FF" stroke-width="2"/>
  <text x="593" y="175" font-size="10" font-family="IBM Plex Mono, monospace" fill="#9BB1FF">API PRINCIPAL · :8080 (dbg :18080)</text>
  <text x="593" y="198" font-size="16" font-weight="600" fill="#F5F3EC">Rust / Axum / Tokio</text>
  <text x="593" y="222" font-size="12" fill="#BDC4D1">Sesiones firmadas HMAC</text>
  <text x="593" y="242" font-size="12" fill="#BDC4D1">aws-sdk-s3 (credenciales R2)</text>
  <text x="593" y="262" font-size="12" fill="#BDC4D1">Cola acotada + concurrencia 1</text>
  <text x="593" y="282" font-size="12" fill="#BDC4D1">Exportación JSON/CSV</text>
  <text x="593" y="302" font-size="12" fill="#BDC4D1">Limpieza TTL 24 h (prefijo)</text>

  <!-- SQLite -->
  <rect x="330" y="385" width="210" height="150" rx="12" fill="#FFFFFF" stroke="#3156D3" stroke-width="1.5"/>
  <text x="348" y="412" font-size="10" font-family="IBM Plex Mono, monospace" fill="#3156D3">VOLUMEN PERSISTENTE</text>
  <text x="348" y="436" font-size="16" font-weight="600" fill="#172B4D">SQLite (WAL)</text>
  <text x="348" y="460" font-size="12" fill="#52617B">Migraciones SQLx</text>
  <text x="348" y="480" font-size="12" fill="#52617B">sessions, jobs, job_windows</text>
  <text x="348" y="500" font-size="12" fill="#52617B">Recuperación tras reinicio</text>

  <!-- Python Inference -->
  <rect x="575" y="385" width="230" height="150" rx="12" fill="#090F1D" stroke="#F0C779" stroke-width="2"/>
  <text x="593" y="412" font-size="10" font-family="IBM Plex Mono, monospace" fill="#FFDF9F">INFERENCIA · :8000 (dbg :18090)</text>
  <text x="593" y="436" font-size="16" font-weight="600" fill="#F5F3EC">Python / FastAPI / PyTorch</text>
  <text x="593" y="460" font-size="12" fill="#BDC4D1">1 proceso · CPU float32</text>
  <text x="593" y="480" font-size="12" fill="#BDC4D1">Log-Mel 64×94 · soxr_hq</text>
  <text x="593" y="500" font-size="12" fill="#BDC4D1">ResNet18 (model.pt :ro)</text>

  <!-- Cloudflare R2 -->
  <rect x="870" y="148" width="210" height="225" rx="14" fill="#FFFFFF" stroke="#3156D3" stroke-width="2"/>
  <text x="890" y="178" font-size="11" font-family="IBM Plex Mono, monospace" fill="#3156D3">NUBE EXTERNA REAL</text>
  <text x="890" y="204" font-size="16" font-weight="600" fill="#172B4D">Cloudflare R2</text>
  <text x="890" y="228" font-size="12" fill="#52617B">Bucket privado (API S3)</text>
  <text x="890" y="248" font-size="12" fill="#52617B">Prefijo doppler/uploads/</text>
  <text x="890" y="268" font-size="12" fill="#52617B">Prefijo pruebas separado</text>
  <text x="890" y="288" font-size="12" fill="#52617B">URLs PUT/GET temporales</text>
  <text x="890" y="308" font-size="12" fill="#52617B">Sin acceso público</text>
  <text x="890" y="338" font-size="11" font-family="IBM Plex Mono, monospace" fill="#3156D3">Credenciales solo en Rust</text>

  <!-- Artefacto local -->
  <rect x="870" y="415" width="210" height="120" rx="14" fill="#FFFFFF" stroke="#172B4D" stroke-width="1.5"/>
  <text x="890" y="443" font-size="10" font-family="IBM Plex Mono, monospace" fill="#52617B">MONTAJE SOLO LECTURA</text>
  <text x="890" y="467" font-size="15" font-weight="600" fill="#172B4D">Checkpoint congelado</text>
  <text x="890" y="490" font-size="12" fill="#52617B">model.pt (SHA-256 verif.)</text>
  <text x="890" y="510" font-size="12" fill="#52617B">inference.json (umbral)</text>

  <!-- Conexiones -->
  <line x1="250" y1="205" x2="328" y2="205" stroke="#3156D3" stroke-width="2" marker-end="url(#arrow)"/>
  <text x="256" y="195" font-size="11" fill="#172B4D">HTTP :4321</text>

  <line x1="540" y1="205" x2="573" y2="205" stroke="#3156D3" stroke-width="2" marker-end="url(#arrow)"/>

  <line x1="805" y1="220" x2="868" y2="220" stroke="#3156D3" stroke-width="2" marker-end="url(#arrow)"/>
  <text x="812" y="210" font-size="10" fill="#172B4D">S3 SigV4</text>

  <line x1="650" y1="333" x2="480" y2="383" stroke="#172B4D" stroke-width="1.8" marker-end="url(#arrowDark)"/>
  <line x1="690" y1="333" x2="690" y2="383" stroke="#3156D3" stroke-width="2" marker-end="url(#arrow)"/>
  <text x="700" y="363" font-size="10" fill="#172B4D">POST /infer</text>

  <line x1="870" y1="472" x2="808" y2="472" stroke="#172B4D" stroke-width="1.8" marker-end="url(#arrowDark)"/>

  <!-- Flecha navegador -> R2 directo -->
  <path d="M 145 130 L 145 90 L 975 90 L 975 146" fill="none" stroke="#3156D3" stroke-width="2" stroke-dasharray="5 3" marker-end="url(#arrow)"/>
  <rect x="360" y="77" width="420" height="22" rx="6" fill="#F5F3EC"/>
  <text x="570" y="92" text-anchor="middle" font-size="11" font-weight="500" fill="#3156D3">Carga directa PUT firmada y reproducción GET temporal (CORS estricto)</text>

  <text x="40" y="600" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">Fuente: implementación local Doppler (docker-compose.yml) · Sección 9.1 / 9.2</text>
</svg>"""


def svg_sequence_diagram() -> str:
    actors = [
        ("Navegador\n(Astro + Svelte)", 110),
        ("Caddy\n(:4321)", 295),
        ("API Rust\n(Axum + SQLite)", 505),
        ("Cloudflare R2\n(Privado S3)", 745),
        ("Inferencia Python\n(ResNet18 CPU)", 975),
    ]
    steps = [
        (0, 2, "1. POST /api/uploads (nombre, tamaño WAV) vía Caddy", "#3156D3"),
        (2, 0, "2. Crea trabajo + clave aleatoria y devuelve URL PUT firmada", "#172B4D"),
        (0, 3, "3. PUT directo del archivo WAV a R2 (progreso real XHR)", "#3156D3"),
        (0, 2, "4. POST /api/jobs/{id}/confirm (idempotente)", "#3156D3"),
        (2, 3, "5. HeadObject: verifica existencia y tamaño real <= 25 MiB", "#52617B"),
        (2, 2, "6. Transición atómica SQLite: uploading → queued → analyzing", "#172B4D"),
        (2, 3, "7. GetObject acotado (descarga WAV con límite estricto)", "#3156D3"),
        (2, 4, "8. POST /infer (WAV) → 16 kHz, peak 0.99, Log-Mel, ResNet18", "#3156D3"),
        (4, 2, "9. Scores sigmoide, clases, hashes SHA-256 y tiempos por etapa", "#172B4D"),
        (2, 0, "10. Persiste en SQLite; UI consulta resultados y GET firmado temporal", "#2643A8"),
    ]
    height = 170 + len(steps) * 52 + 60
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1120 {height}" width="1120" height="{height}" font-family="IBM Plex Sans, sans-serif">',
        """  <defs>
    <marker id="seqArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#3156D3"/>
    </marker>
  </defs>""",
        f'  <rect width="1120" height="{height}" fill="#F5F3EC"/>',
        '  <text x="40" y="42" font-size="22" font-weight="600" fill="#172B4D">Secuencia de carga, inferencia y consulta — Doppler</text>',
        '  <text x="40" y="65" font-size="13" fill="#52617B">Flujo real implementado con credenciales R2 aisladas en Rust y cola persistente en SQLite</text>',
    ]
    for name, x in actors:
        lines = name.split("\n")
        parts.append(
            f'  <rect x="{x - 82}" y="86" width="164" height="52" rx="10" fill="#090F1D" stroke="#34435C" stroke-width="1.5"/>'
        )
        parts.append(
            f'  <text x="{x}" y="109" text-anchor="middle" font-size="12" font-weight="600" fill="#F5F3EC">{esc(lines[0])}</text>'
        )
        parts.append(
            f'  <text x="{x}" y="126" text-anchor="middle" font-size="10" font-family="IBM Plex Mono, monospace" fill="#9BB1FF">{esc(lines[1])}</text>'
        )
        parts.append(
            f'  <line x1="{x}" y1="138" x2="{x}" y2="{height - 46}" stroke="#BDC4D1" stroke-dasharray="5 5" stroke-width="1.5"/>'
        )

    for idx, (src, dst, label, color) in enumerate(steps):
        y = 175 + idx * 52
        x1 = actors[src][1]
        x2 = actors[dst][1]
        if src == dst:
            parts.append(
                f'  <path d="M {x1} {y - 8} H {x1 + 52} V {y + 12} H {x1 + 4}" fill="none" stroke="{color}" stroke-width="2" marker-end="url(#seqArrow)"/>'
            )
            parts.append(
                f'  <text x="{x1 + 60}" y="{y + 5}" font-size="11.5" font-weight="500" fill="#172B4D">{esc(label)}</text>'
            )
        else:
            dx = 8 if x2 > x1 else -8
            parts.append(
                f'  <line x1="{x1}" y1="{y}" x2="{x2 - dx}" y2="{y}" stroke="{color}" stroke-width="2" marker-end="url(#seqArrow)"/>'
            )
            tx = min(x1, x2) + 14
            parts.append(
                f'  <rect x="{tx - 4}" y="{y - 22}" width="{len(label) * 6.5 + 10:.0f}" height="18" rx="4" fill="#F5F3EC" fill-opacity="0.92"/>'
            )
            parts.append(
                f'  <text x="{tx}" y="{y - 9}" font-size="11.5" font-weight="500" fill="#172B4D">{esc(label)}</text>'
            )

    parts.append(
        f'  <text x="40" y="{height - 16}" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">Fuente: contrato OpenAPI y flujo ejecutado en validación local · Sección 9.1</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def svg_cpu_latency_chart(bench: dict) -> str:
    conditions = bench.get("conditions", [])
    if not conditions:
        return ""
    width, height = 1040, 540
    left, right, top, bottom = 95, 45, 105, 110
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_val = max(float(c["total_p95_ms"]) for c in conditions) * 1.18
    max_val = max(max_val, 10.0)

    n_obs = bench.get("observations_per_condition", 30)
    threads = bench.get("torch_num_threads", 4)
    startup = bench.get("startup_model_load_ms", 0)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" font-family="IBM Plex Sans, sans-serif">',
        f'  <rect width="{width}" height="{height}" fill="#FFFFFF"/>',
        '  <text x="40" y="38" font-size="20" font-weight="600" fill="#172B4D">Latencia CPU local por duración de audio WAV (p50 y p95)</text>',
        f'  <text x="40" y="60" font-size="12.5" fill="#52617B">Validación local en CPU · n = {n_obs} ejecuciones calientes por condición · {threads} hilos PyTorch · concurrencia = 1 · carga inicial del modelo: {startup:.1f} ms</text>',
        # Leyenda
        '  <rect x="40" y="74" width="14" height="12" rx="2" fill="#3156D3"/><text x="60" y="84" font-size="11.5" fill="#172B4D">Total p50 (ms)</text>',
        '  <rect x="175" y="74" width="14" height="12" rx="2" fill="#172B4D"/><text x="195" y="84" font-size="11.5" fill="#172B4D">Total p95 (ms)</text>',
        '  <rect x="310" y="74" width="14" height="12" rx="2" fill="#9BB1FF"/><text x="330" y="84" font-size="11.5" fill="#172B4D">Inferencia p50 (ms)</text>',
        '  <rect x="475" y="74" width="14" height="12" rx="2" fill="#F0C779"/><text x="495" y="84" font-size="11.5" fill="#172B4D">Preparación p50 (ms)</text>',
    ]

    # Grid Y
    for i in range(6):
        val = (max_val / 5.0) * i
        y = top + plot_h - (val / max_val) * plot_h
        parts.append(f'  <line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#D7D9DF" stroke-width="1"/>')
        parts.append(
            f'  <text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">{val:.0f}</text>'
        )

    parts.append(
        f'  <text x="26" y="{top + plot_h / 2:.1f}" transform="rotate(-90 26 {top + plot_h / 2:.1f})" text-anchor="middle" font-size="12" fill="#172B4D">Tiempo (milisegundos)</text>'
    )
    parts.append(f'  <line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" stroke="#172B4D" stroke-width="1.5"/>')

    group_w = plot_w / len(conditions)
    bar_w = min(38.0, group_w / 5.4)
    series = [
        ("prepare_p50_ms", "#F0C779"),
        ("inference_p50_ms", "#9BB1FF"),
        ("total_p50_ms", "#3156D3"),
        ("total_p95_ms", "#172B4D"),
    ]

    for g_idx, cond in enumerate(conditions):
        gx = left + g_idx * group_w + (group_w - len(series) * (bar_w + 6)) / 2
        for s_idx, (key, color) in enumerate(series):
            val = float(cond[key])
            bh = (val / max_val) * plot_h
            bx = gx + s_idx * (bar_w + 6)
            by = top + plot_h - bh
            parts.append(f'  <rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="4" fill="{color}"/>')
            parts.append(
                f'  <text x="{bx + bar_w / 2:.1f}" y="{by - 6:.1f}" text-anchor="middle" font-size="10" font-family="IBM Plex Mono, monospace" fill="#172B4D">{val:.0f}</text>'
            )
        cx = left + (g_idx + 0.5) * group_w
        parts.append(
            f'  <text x="{cx:.1f}" y="{top + plot_h + 24}" text-anchor="middle" font-size="12.5" font-weight="600" fill="#172B4D">{cond["duration_seconds"]:.0f} s ({cond["windows_total"]} vent.)</text>'
        )

    parts.append(
        f'  <text x="40" y="{height - 22}" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">Procedencia: benchmark_cpu_resumen.json · Fixtures WAV sintéticas PCM16 16 kHz mono · Validación local (no servidor de producción)</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def svg_memory_chart(mem_summary: dict) -> str:
    services = mem_summary.get("services", {})
    if not services:
        return ""
    width, height = 1040, 480
    left, right, top, bottom = 95, 45, 95, 95
    plot_w = width - left - right
    plot_h = height - top - bottom

    items: list[tuple[str, float, float]] = []
    for svc, vals in services.items():
        short_name = svc.replace("doppler-", "").replace("-1", "")
        items.append((short_name, float(vals["reposo_mean_mib"]), float(vals["max_mib"])))
    stack = mem_summary.get("stack_total_mib", {})
    items.append(("Total conjunto", float(stack.get("mean", 0)), float(stack.get("max", 0))))

    max_val = max(max(a, b) for _, a, b in items)
    y_max = max(max_val * 1.25, 2200.0)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" font-family="IBM Plex Sans, sans-serif">',
        f'  <rect width="{width}" height="{height}" fill="#FFFFFF"/>',
        '  <text x="40" y="38" font-size="20" font-weight="600" fill="#172B4D">Consumo de memoria por servicio y conjunto (MiB)</text>',
        f'  <text x="40" y="58" font-size="12.5" fill="#52617B">Muestreo: docker stats cada {mem_summary.get("sampling_interval_seconds", 1.0)} s · n = {mem_summary.get("total_samples", 0)} registros · línea de referencia 2048 MiB</text>',
        '  <rect x="40" y="70" width="14" height="12" rx="2" fill="#9BB1FF"/><text x="60" y="80" font-size="11.5" fill="#172B4D">Media en reposo (MiB)</text>',
        '  <rect x="225" y="70" width="14" height="12" rx="2" fill="#3156D3"/><text x="245" y="80" font-size="11.5" fill="#172B4D">Pico observado bajo carga (MiB)</text>',
    ]

    for i in range(6):
        val = (y_max / 5.0) * i
        y = top + plot_h - (val / y_max) * plot_h
        parts.append(f'  <line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#D7D9DF" stroke-width="1"/>')
        parts.append(
            f'  <text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">{val:.0f}</text>'
        )

    # Línea referencia 2048 MiB
    y_ref = top + plot_h - (2048.0 / y_max) * plot_h
    parts.append(f'  <line x1="{left}" y1="{y_ref:.1f}" x2="{width - right}" y2="{y_ref:.1f}" stroke="#C27D0E" stroke-dasharray="6 4" stroke-width="1.8"/>')
    parts.append(
        f'  <text x="{width - right - 4}" y="{y_ref - 6:.1f}" text-anchor="end" font-size="11" font-family="IBM Plex Mono, monospace" fill="#744A00">Referencia nominal 2048 MiB (sin SO ni margen de pico VPS)</text>'
    )

    parts.append(f'  <line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" stroke="#172B4D" stroke-width="1.5"/>')

    group_w = plot_w / len(items)
    bar_w = min(56.0, group_w / 3.4)
    for idx, (label, idle_mib, max_mib) in enumerate(items):
        gx = left + idx * group_w + (group_w - (bar_w * 2 + 12)) / 2
        for s_idx, (val, color) in enumerate([(idle_mib, "#9BB1FF"), (max_mib, "#3156D3")]):
            bh = (val / y_max) * plot_h
            bx = gx + s_idx * (bar_w + 12)
            by = top + plot_h - bh
            parts.append(f'  <rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="4" fill="{color}"/>')
            parts.append(
                f'  <text x="{bx + bar_w / 2:.1f}" y="{by - 6:.1f}" text-anchor="middle" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#172B4D">{val:.1f}</text>'
            )
        cx = left + (idx + 0.5) * group_w
        parts.append(
            f'  <text x="{cx:.1f}" y="{top + plot_h + 24}" text-anchor="middle" font-size="12.5" font-weight="600" fill="#172B4D">{esc(label)}</text>'
        )

    parts.append(
        f'  <text x="40" y="{height - 20}" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">Procedencia: memoria_servicios_resumen.json · Validación local Docker en Manjaro (no equivale a consumo total de un VPS de 2 GB)</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def svg_pipeline_stages_chart(integration: dict) -> str:
    e2e = integration.get("tests", {}).get("end_to_end_real_r2_and_inference", {})
    timings = e2e.get("timings", {})
    if not timings:
        return ""
    stages = [
        ("Transferencia cliente → R2", float(e2e.get("upload_ms", 0.0)), "#3156D3"),
        ("Espera en cola SQLite", float(timings.get("queue_wait_ms") or 0.0), "#949FB3"),
        ("Descarga Rust ← R2", float(timings.get("r2_fetch_ms") or 0.0), "#5275EF"),
        ("Decodificación y Log-Mel", float(timings.get("decode_and_prepare_ms") or 0.0), "#F0C779"),
        ("Inferencia ResNet18 CPU", float(timings.get("inference_ms") or 0.0), "#172B4D"),
        ("Persistencia SQLite", float(timings.get("persist_ms") or 0.0), "#86D6B8"),
    ]
    width, height = 1040, 420
    left, right, top = 260, 110, 96
    bar_area = width - left - right
    max_val = max(v for _, v, _ in stages) * 1.15
    max_val = max(max_val, 10.0)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" font-family="IBM Plex Sans, sans-serif">',
        f'  <rect width="{width}" height="{height}" fill="#FFFFFF"/>',
        '  <text x="40" y="38" font-size="20" font-weight="600" fill="#172B4D">Desglose de tiempos por etapa del flujo real con Cloudflare R2</text>',
        '  <text x="40" y="60" font-size="12.5" fill="#52617B">Audio sintético WAV de 6,0 s (3 ventanas) · ejecución real extremo a extremo vía Caddy → Rust → R2 → Python</text>',
    ]
    for idx, (label, val, color) in enumerate(stages):
        y = top + idx * 46
        bw = max(3.0, (val / max_val) * bar_area)
        parts.append(
            f'  <text x="{left - 14}" y="{y + 20}" text-anchor="end" font-size="12.5" fill="#172B4D">{esc(label)}</text>'
        )
        parts.append(f'  <rect x="{left}" y="{y + 4}" width="{bw:.1f}" height="24" rx="5" fill="{color}"/>')
        parts.append(
            f'  <text x="{left + bw + 10:.1f}" y="{y + 20}" font-size="11.5" font-family="IBM Plex Mono, monospace" fill="#172B4D">{val:.2f} ms</text>'
        )

    parts.append(
        f'  <text x="40" y="{height - 20}" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">Procedencia: pruebas_integracion.json · Validación local con almacenamiento real en Cloudflare R2</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def convert_svgs_to_pngs(svg_paths: list[Path]) -> None:
    if not svg_paths:
        return
    js_script = """
const { chromium } = require('@playwright/test');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 2 });
  for (const svgPath of process.argv.slice(1)) {
    const svgText = fs.readFileSync(svgPath, 'utf8');
    const wMatch = svgText.match(/width="(\\d+)"/);
    const hMatch = svgText.match(/height="(\\d+)"/);
    const w = wMatch ? parseInt(wMatch[1], 10) : 1120;
    const h = hMatch ? parseInt(hMatch[1], 10) : 600;
    await page.setViewportSize({ width: w, height: h });
    await page.setContent(`<!doctype html><html><body style="margin:0;padding:0;background:transparent;">${svgText}</body></html>`);
    await page.screenshot({ path: svgPath.replace(/\\.svg$/, '.png'), fullPage: false });
  }
  await browser.close();
})();
"""
    proc = subprocess.run(
        ["node", "-e", js_script, *[str(p) for p in svg_paths]],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Error convirtiendo SVG a PNG con Playwright: {proc.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir: Path = args.run_dir

    diag_dir = run_dir / "diagramas"
    chart_dir = run_dir / "graficas"
    diag_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)

    svgs: list[Path] = []

    p1 = diag_dir / "diagrama_componentes.svg"
    p1.write_text(svg_components_diagram(), encoding="utf-8")
    svgs.append(p1)

    p2 = diag_dir / "diagrama_secuencia_carga_inferencia.svg"
    p2.write_text(svg_sequence_diagram(), encoding="utf-8")
    svgs.append(p2)

    bench_path = run_dir / "benchmark_cpu_resumen.json"
    if bench_path.is_file():
        svg = svg_cpu_latency_chart(json.loads(bench_path.read_text(encoding="utf-8")))
        if svg:
            p = chart_dir / "latencia_cpu_p50_p95.svg"
            p.write_text(svg, encoding="utf-8")
            svgs.append(p)

    mem_path = run_dir / "memoria_servicios_resumen.json"
    if mem_path.is_file():
        svg = svg_memory_chart(json.loads(mem_path.read_text(encoding="utf-8")))
        if svg:
            p = chart_dir / "memoria_servicios_docker.svg"
            p.write_text(svg, encoding="utf-8")
            svgs.append(p)

    int_path = run_dir / "pruebas_integracion.json"
    if int_path.is_file():
        svg = svg_pipeline_stages_chart(json.loads(int_path.read_text(encoding="utf-8")))
        if svg:
            p = chart_dir / "desglose_etapas_pipeline.svg"
            p.write_text(svg, encoding="utf-8")
            svgs.append(p)

    convert_svgs_to_pngs(svgs)
    print(f"Generados {len(svgs)} diagramas/gráficas en SVG y PNG.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
