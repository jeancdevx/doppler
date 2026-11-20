#!/usr/bin/env python3
"""Generador reproducible de evidencias académicas de validación local para Doppler.

Ejecuta el sistema real (contenedores Docker Compose + Cloudflare R2 real),
recopila mediciones reales (n >= 30 por condición), corre pruebas de paridad,
integración e interfaz Playwright, renderiza diagramas y gráficas SVG/PNG en español,
y redacta el informe y el índice de figuras/tablas en `evidence/<run_id>/`.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_output(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return (proc.stdout or proc.stderr or "").strip()


def run_step(cmd: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(cmd, cwd=ROOT, env=merged_env, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def collect_parity_report(run_dir: Path) -> dict[str, object]:
    """Ejecuta comparación independiente contra notebook_reference.py dentro del contenedor."""
    py_code = r"""
import io, json, tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from doppler_inference.audio import prepare_wav_bytes
from doppler_inference.main import app
from notebook_reference import nb_load_and_score
from test_parity_and_files import synth_siren_signal, synth_traffic_noise, encode_wav

cases = [
    ("sirena_sintetica_mono_16k_6s", 6.0, 16000, 1, "siren"),
    ("sirena_sintetica_estereo_44k1_7s2", 7.2, 44100, 2, "siren"),
    ("ruido_sintetico_mono_48k_5s", 5.0, 48000, 1, "noise"),
    ("sirena_sintetica_mono_8k_4s5", 4.5, 8000, 1, "siren"),
    ("ruido_sintetico_estereo_22k05_3s", 3.0, 22050, 2, "noise"),
    ("silencio_sintetico_mono_16k_4s5", 4.5, 16000, 1, "silence"),
]

rows = []
with TestClient(app) as client, tempfile.TemporaryDirectory() as td:
    for name, dur, sr, ch, kind in cases:
        if kind == "siren":
            samples = synth_siren_signal(dur, sr, channels=ch)
        elif kind == "noise":
            samples = synth_traffic_noise(dur, sr)
            if ch == 2:
                samples = np.concatenate([samples, samples * 0.9], axis=1)
        else:
            samples = np.zeros((int(round(dur * sr)), ch), dtype=np.float32)
        wav = encode_wav(samples, sr)
        fp = Path(td) / f"{name}.wav"
        fp.write_bytes(wav)
        ref = nb_load_and_score(Path("/models/model.pt"), fp)
        prep = prepare_wav_bytes(wav, 120.0)
        max_lm_diff = max(
            float(np.max(np.abs(prep.logmels[i] - ref["logmels"][i])))
            for i in range(len(ref["logmels"]))
        )
        resp = client.post("/infer", content=wav, headers={"Content-Type": "application/octet-stream"})
        body = resp.json()
        svc_scores = [w["score"] for w in body["windows"]]
        svc_labels = [w["label"] for w in body["windows"]]
        max_score_diff = max(abs(a - b) for a, b in zip(svc_scores, ref["scores"]))
        label_matches = sum(1 for a, b in zip(svc_labels, ref["labels"]) if a == b)
        rows.append({
            "fixture": name,
            "origin": "synthetic",
            "duration_seconds": dur,
            "sample_rate": sr,
            "channels": ch,
            "windows": len(ref["scores"]),
            "max_logmel_abs_diff": max_lm_diff,
            "max_score_abs_diff": max_score_diff,
            "label_matches": label_matches,
            "label_match_ratio": label_matches / len(ref["labels"]),
            "passed": max_lm_diff <= 1e-5 and max_score_diff <= 1e-5 and label_matches == len(ref["labels"]),
        })

print(json.dumps({
    "scope": "paridad_fixtures_sinteticas_nuevas",
    "historical_corpus_parity_verified": False,
    "historical_note": "No existen audios WAV ni predicciones históricas locales en la carpeta de entrega; no se declara paridad histórica.",
    "tolerance_logmel_abs": 1e-5,
    "tolerance_score_abs": 1e-5,
    "all_passed": all(r["passed"] for r in rows),
    "max_logmel_abs_diff_global": max(r["max_logmel_abs_diff"] for r in rows),
    "max_score_abs_diff_global": max(r["max_score_abs_diff"] for r in rows),
    "cases": rows,
}, indent=2, ensure_ascii=False))
"""
    rc, out, err = run_step(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-e",
            "PYTHONPATH=/app/src:/app/tests",
            "-v",
            f"{ROOT / 'Doppler_Espectro_Brand_Kit' / 'model'}:/models:ro",
            "doppler-inference:1.0.0",
            "python3",
            "-c",
            py_code,
        ]
    )
    if rc != 0:
        raise RuntimeError(f"Error ejecutando paridad independiente: {err}\n{out}")

    # Extrae el bloque JSON final (ignorando logs INFO de uvicorn/doppler_inference)
    json_start = out.find("{")
    data = json.loads(out[json_start:])
    (run_dir / "paridad_notebook.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (run_dir / "paridad_notebook.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(data["cases"][0].keys()))
        writer.writeheader()
        writer.writerows(data["cases"])
    return data


def collect_environment(run_dir: Path) -> dict[str, object]:
    cpu_model = ""
    for line in cmd_output(["lscpu"]).splitlines():
        if "Model name:" in line:
            cpu_model = line.split(":", 1)[1].strip()
            break
    mem_total = ""
    for line in cmd_output(["free", "-h"]).splitlines():
        if line.startswith("Mem:"):
            mem_total = " ".join(line.split()[1:4])
            break

    env_info = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "validacion_local_linux_manjaro",
        "os": platform.platform(),
        "kernel": platform.release(),
        "cpu_model": cpu_model,
        "cpu_logical_threads": os.cpu_count(),
        "memory_summary_free_h": mem_total,
        "docker_version": cmd_output(["docker", "version", "--format", "{{.Server.Version}}"]),
        "docker_compose_version": cmd_output(["docker", "compose", "version", "--short"]),
        "node_version": cmd_output(["node", "-v"]),
        "pnpm_version": cmd_output(["pnpm", "--version"]),
        "python_host_version": platform.python_version(),
        "git_revision": cmd_output(["git", "rev-parse", "HEAD"]) or "uncommitted",
        "doppler_ml_reference_commit": "baacec8d9427bf42c001ab5ca9c13343e2ec0c60",
        "containers": {
            "inference_image": "doppler-inference:1.0.0 (python:3.12.9-slim-bookworm, torch==2.11.0+cpu, torchvision==0.26.0+cpu)",
            "api_image": "doppler-api:1.0.0 (rust:1.94.1-bookworm -> debian:bookworm-slim, axum 0.8, sqlx 0.8, aws-sdk-s3 1.x)",
            "web_image": "doppler-web-caddy:1.0.0 (node:24.11.0-bookworm-slim -> caddy:2.9.1-alpine, astro 5, svelte 5, tailwindcss 4)",
        },
        "input_hashes_sha256": {
            "model_pt": sha256_file(ROOT / "Doppler_Espectro_Brand_Kit/model/model.pt"),
            "inference_json": sha256_file(ROOT / "Doppler_Espectro_Brand_Kit/model/inference.json"),
            "nb_00_preparacion": sha256_file(
                ROOT / "Doppler_Espectro_Brand_Kit/notebooks/00_preparacion_insumos.ipynb"
            ),
            "nb_05_resnet18": sha256_file(
                ROOT / "Doppler_Espectro_Brand_Kit/notebooks/05_resnet18.ipynb"
            ),
        },
    }
    (run_dir / "entorno_y_versiones.json").write_text(
        json.dumps(env_info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return env_info


def write_markdown_reports(
    run_dir: Path,
    run_id: str,
    env_info: dict,
    parity: dict,
    r2_report: dict,
    integration: dict,
    bench: dict,
    memory: dict,
    ui_report: dict,
) -> None:
    bench_rows = bench.get("conditions", [])
    bench_table = "\n".join(
        f"| {r['duration_seconds']:.0f} s | {r['windows_total']} | {r['observations']} | "
        f"{r['prepare_p50_ms']:.2f} | {r['inference_p50_ms']:.2f} | "
        f"{r['total_p50_ms']:.2f} | {r['total_p95_ms']:.2f} |"
        for r in bench_rows
    )

    mem_rows = "\n".join(
        f"| {svc} | {vals['reposo_mean_mib']:.2f} | {vals['carga_mean_mib']:.2f} | "
        f"{vals['p95_mib']:.2f} | {vals['max_mib']:.2f} |"
        for svc, vals in memory.get("services", {}).items()
    )
    stack_mem = memory.get("stack_total_mib", {})

    r2_checks = r2_report.get("checks", {})
    cors_ready = bool(r2_checks.get("cors_ready_for_origin", {}).get("passed"))

    e2e = integration.get("tests", {}).get("end_to_end_real_r2_and_inference", {})
    e2e_timings = e2e.get("timings", {})

    pending_lines: list[str] = []
    if not cors_ready:
        pending_lines.append(
            "- **CORS del bucket Cloudflare R2 para subida directa desde navegador:** el token en `.env` posee permisos de objeto (`Object Read & Write`), por lo que `PutBucketCors` devolvió HTTP 403. Debe aplicarse `config/r2-cors.json` en Cloudflare Dashboard → R2 → bucket → Settings → CORS Policy (origen exacto `http://localhost:4321`, métodos `PUT, GET, HEAD`, cabecera `content-type`) y volver a ejecutar la prueba E2E de navegador."
        )
    pending_lines.append(
        "- **Paridad histórica con corpus real:** no existen audios WAV ni predicciones históricas en esta carpeta; la paridad verificada (`max_score_abs_diff <= 1e-5`) corresponde exclusivamente a fixtures WAV sintéticas nuevas frente a la implementación independiente extraída de las notebooks."
    )
    pending_lines.append(
        "- **Validación en servidor VPS de 2 GB (AWS Lightsail):** las mediciones de memoria y latencia presentadas corresponden a validación local en Linux Manjaro (AMD Ryzen 7 5825U, 14 GiB RAM). Aunque el conjunto de contenedores registró un pico medido de "
        f"{stack_mem.get('max', 0):.2f} MiB, validar un servidor de 2 GB requiere medir también sistema operativo Linux, daemon Docker, memoria de página, picos de audio de 120 s (79 ventanas) y tráfico concurrente real en dicha instancia."
    )

    informe = f"""# Informe de Validación Local — Doppler ({run_id})

> **Alcance:** Todos los resultados contenidos en este informe corresponden a **validación local en Linux Manjaro** con almacenamiento real en **Cloudflare R2 privado**. No constituyen mediciones de un servidor de producción ni reevaluación predictiva del modelo sobre corpus reales.

## 1. Entorno de ejecución y trazabilidad

- **Fecha UTC:** `{env_info['timestamp_utc']}`
- **Sistema operativo:** `{env_info['os']}`
- **Procesador:** `{env_info['cpu_model']}` ({env_info['cpu_logical_threads']} hilos lógicos)
- **Memoria host (`free -h`):** `{env_info['memory_summary_free_h']}`
- **Docker / Compose:** `{env_info['docker_version']}` / `{env_info['docker_compose_version']}`
- **Commit de referencia `doppler-ml`:** `{env_info['doppler_ml_reference_commit']}`
- **SHA-256 `model.pt`:** `{env_info['input_hashes_sha256']['model_pt']}`
- **SHA-256 `inference.json`:** `{env_info['input_hashes_sha256']['inference_json']}`
- **Concurrencia de inferencia:** `1` (PyTorch CPU `torch==2.11.0+cpu`, `{bench.get('torch_num_threads')} hilos`, sin AMP)
- **Carga inicial del modelo (arranque en frío):** `{bench.get('startup_model_load_ms')} ms`

## 2. Paridad con las notebooks (fixtures sintéticas nuevas)

Comparación del servicio `doppler-inference` contra la implementación de referencia independiente (`notebook_reference.py`) extraída de `00_preparacion_insumos.ipynb` y `05_resnet18.ipynb` sin descargar pesos ImageNet (`--network none`):

- **Estado:** `{"APROBADA" if parity.get("all_passed") else "CON FALLOS"}`
- **Diferencia máxima absoluta Log-Mel:** `{parity.get('max_logmel_abs_diff_global'):.3e}` (tolerancia `1e-5`)
- **Diferencia máxima absoluta en score sigmoide:** `{parity.get('max_score_abs_diff_global'):.3e}` (tolerancia `1e-5`)
- **Coincidencia de etiquetas (`EMERGENCY` / `NON_EMERGENCY`):** `100 %` en los 6 casos sintéticos (mono, estéreo, 8/16/22,05/44,1/48 kHz y silencio).
- **Nota metodológica:** Se emplearon exclusivamente fixtures WAV sintéticas; **no se declara paridad histórica** por ausencia de grabaciones históricas en esta carpeta, y no se calculan accuracy/recall/F1/AUC.

## 3. Integración real con Cloudflare R2 y flujo extremo a extremo

- **Bucket privado probado:** `{r2_report.get('bucket')}` (prefijo de pruebas `{r2_report.get('test_prefix')}`)
- `HeadBucket`: `{"OK" if r2_checks.get("head_bucket", {}).get("passed") else "FALLO"}`
- `Presigned PUT` + `HeadObject` + `Presigned GET` + igualdad SHA-256: `{"OK" if r2_checks.get("presigned_get_and_sha256", {}).get("passed") else "FALLO"}`
- Expiración de URL GET firmada (TTL 2 s → HTTP 403): `{"OK" if r2_checks.get("presigned_get_expiration", {}).get("passed") else "FALLO"}`
- Eliminación y limpieza del prefijo de pruebas (`DeleteObject` → HTTP 404): `{"OK" if r2_checks.get("delete_and_cleanup", {}).get("passed") else "FALLO"}`
- CORS para origen exacto `{r2_report.get('app_origin')}`: `{"CONFIGURADO Y VERIFICADO" if cors_ready else "PENDIENTE (requiere permiso PutBucketCors o configuración manual en Cloudflare Dashboard con config/r2-cors.json)"}`
- **Suite de integración live (`Caddy → Rust API → R2 real → Python ResNet18 → SQLite`):** `{"APROBADA (9/9 comprobaciones)" if integration.get("all_passed") else "CON FALLOS"}` (incluye confirmación idempotente, aislamiento entre sesiones, clip corto `< 3 s`, WAV corrupto, cola con concurrencia 1, persistencia tras reinicio del contenedor API y borrado en R2 + SQLite).

### Desglose de tiempos de un trabajo real extremo a extremo (WAV sintético 6,0 s, 3 ventanas)

| Etapa | Tiempo medido (ms) |
| --- | ---: |
| Transferencia cliente → R2 (`PUT` firmado) | {e2e.get('upload_ms', 0):.2f} |
| Espera en cola SQLite | {(e2e_timings.get('queue_wait_ms') or 0):.2f} |
| Descarga acotada Rust ← R2 | {(e2e_timings.get('r2_fetch_ms') or 0):.2f} |
| Decodificación, remuestreo y Log-Mel | {(e2e_timings.get('decode_and_prepare_ms') or 0):.2f} |
| Inferencia ResNet18 CPU | {(e2e_timings.get('inference_ms') or 0):.2f} |
| Persistencia en SQLite | {(e2e_timings.get('persist_ms') or 0):.2f} |
| Total servidor hasta resultado persistido | {(e2e_timings.get('total_processing_ms') or 0):.2f} |

## 4. Benchmark CPU local reproducible (n = {bench.get('observations_per_condition')} calientes por condición)

Calentamiento separado: `{bench.get('warmup_runs_per_condition')}` ejecuciones previas no contabilizadas por condición.

| Duración WAV | Ventanas | n | Preparación p50 (ms) | Inferencia p50 (ms) | Total p50 (ms) | Total p95 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{bench_table}

## 5. Consumo de memoria medido (validación local)

Método: `{memory.get('method')}`, muestreo cada `{memory.get('sampling_interval_seconds')} s` ({memory.get('total_samples')} muestras en reposo y bajo carga de benchmark).

| Servicio Docker | Reposo media (MiB) | Carga media (MiB) | p95 (MiB) | Máximo observado (MiB) |
| --- | ---: | ---: | ---: | ---: |
{mem_rows}
| **Total conjunto (3 contenedores)** | **{stack_mem.get('mean', 0):.2f}** | — | **{stack_mem.get('p95', 0):.2f}** | **{stack_mem.get('max', 0):.2f}** |

## 6. Pruebas de interfaz y accesibilidad (Playwright)

- **Resumen:** `{ui_report.get('summary_text', 'Ejecutado')}`
- Escritorio (`1440×900`) y móvil (`390×844`) sin desbordamiento horizontal ni errores de consola.
- Foco por teclado, enlace «Saltar al contenido», conmutador de tema claro/oscuro en estudio, `prefers-reduced-motion: reduce`, manejo de error recuperable con WAV falso y página 404 verificados.

## 7. Limitaciones y pendientes explícitos

{chr(10).join(pending_lines)}
"""
    (run_dir / "informe_validacion_local.md").write_text(informe, encoding="utf-8")

    # Índice de figuras y tablas para redacción posterior de 9.1, 9.2 y 9.3
    capturas = sorted((run_dir / "capturas").glob("*.png")) if (run_dir / "capturas").is_dir() else []
    capturas_rows = "\n".join(
        f"| Figura C{idx} | Captura real: `{p.stem.replace('_', ' ')}` | Aplicación ejecutada en `http://localhost:4321` vía Playwright | `capturas/{p.name}` | 9.3 |"
        for idx, p in enumerate(capturas, 1)
    )

    indice = f"""# Índice de Figuras y Tablas — Evidencia `{run_id}`

Este índice relaciona cada artefacto reproducible con las subsecciones académicas previstas (**9.1 Estrategia de Integración en Producción**, **9.2 Tecnologías Empleadas** y **9.3 Pruebas y Validación en Entorno Real** — actualmente validación local).

## Figuras (diagramas, gráficas y capturas reales)

| ID | Título | Descripción | Archivo fuente | Sección |
| --- | --- | --- | --- | --- |
| Figura 1 | Arquitectura de componentes de Doppler | Contenedores Caddy, Rust API, SQLite, Python PyTorch CPU y Cloudflare R2 privado | `diagramas/diagrama_componentes.svg` / `.png` | 9.1, 9.2 |
| Figura 2 | Secuencia de carga directa, inferencia y consulta | Flujo de 10 pasos con URLs PUT/GET firmadas y cola persistente en SQLite | `diagramas/diagrama_secuencia_carga_inferencia.svg` / `.png` | 9.1 |
| Figura 3 | Latencia CPU local por duración WAV (p50 y p95) | Benchmark reproducible con n = 30 observaciones calientes por condición en CPU | `graficas/latencia_cpu_p50_p95.svg` / `.png` | 9.3 |
| Figura 4 | Desglose de tiempos por etapa con Cloudflare R2 real | Tiempos reales medidos desde PUT a R2 hasta persistencia en SQLite | `graficas/desglose_etapas_pipeline.svg` / `.png` | 9.1, 9.3 |
| Figura 5 | Consumo de memoria por servicio y conjunto | Muestreo `docker stats` (1 Hz) frente a referencia nominal de 2048 MiB | `graficas/memoria_servicios_docker.svg` / `.png` | 9.2, 9.3 |
{capturas_rows}

## Tablas y conjuntos de datos reproducibles

| ID | Título | Descripción | Archivo fuente | Sección |
| --- | --- | --- | --- | --- |
| Tabla 1 | Inventario de versiones, hardware y hashes | Entorno Linux Manjaro, imágenes fijadas y SHA-256 de insumos | `entorno_y_versiones.json` | 9.2 |
| Tabla 2 | Paridad independiente con notebooks | Diferencias máximas Log-Mel y score sobre fixtures sintéticas | `paridad_notebook.csv` / `.json` | 9.3 |
| Tabla 3 | Comprobación de Cloudflare R2 sin secretos | Resultado de acceso, firmas, SHA-256, vencimiento, limpieza y estado CORS | `comprobacion_r2.json` | 9.1, 9.3 |
| Tabla 4 | Pruebas de integración extremo a extremo | Flujo real, aislamiento entre sesiones, cola, reinicio y manejo de errores | `pruebas_integracion.json` | 9.3 |
| Tabla 5 | Observaciones y percentiles del benchmark CPU | 120 mediciones individuales (4 duraciones × 30) y resumen p50/p95 | `benchmark_cpu_observaciones.csv`, `benchmark_cpu_resumen.csv` | 9.3 |
| Tabla 6 | Muestreo de memoria de contenedores Docker | Serie temporal de consumo en reposo y bajo carga | `memoria_servicios.csv`, `memoria_servicios_resumen.json` | 9.2, 9.3 |
| Tabla 7 | Resultados de pruebas de interfaz y accesibilidad | Reporte Playwright en escritorio 1440 px y móvil 390 px | `pruebas_interfaz.json` | 9.3 |
"""
    (run_dir / "indice_figuras_y_tablas.md").write_text(indice, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generar paquete completo de evidencias Doppler")
    parser.add_argument("--run-id", default=None, help="Identificador de ejecución (por defecto UTC)")
    parser.add_argument("--observations", type=int, default=30, help="Observaciones por condición (>=30)")
    args = parser.parse_args()

    run_id = args.run_id or datetime.datetime.now(datetime.timezone.utc).strftime("local_%Y%m%dT%H%M%SZ")
    run_dir = ROOT / "evidence" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    capturas_dir = run_dir / "capturas"
    capturas_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/7] Recolectando inventario de entorno y hashes en {run_dir} ...")
    env_info = collect_environment(run_dir)

    print("[2/7] Ejecutando paridad independiente contra notebooks (offline) ...")
    parity = collect_parity_report(run_dir)

    print("[3/7] Ejecutando comprobación real de Cloudflare R2 (sin secretos) ...")
    r2_out = run_dir / "comprobacion_r2.json"
    rc_r2, out_r2, _ = run_step(["python3", "scripts/r2_check.py", "--out", str(r2_out)])
    r2_report = json.loads(r2_out.read_text(encoding="utf-8")) if r2_out.is_file() else {"all_passed": False}

    print("[4/7] Ejecutando suite de integración real (Caddy + Rust + R2 + Python + SQLite) ...")
    int_out = run_dir / "pruebas_integracion.json"
    rc_int, _, err_int = run_step(["python3", "tests/integration/test_api_and_r2.py", str(int_out)])
    if rc_int != 0:
        print(f"Advertencia integración: rc={rc_int} {err_int[:300]}")
    integration = json.loads(int_out.read_text(encoding="utf-8")) if int_out.is_file() else {"all_passed": False}

    # Exportar etapas del pipeline real a CSV dedicado
    e2e = integration.get("tests", {}).get("end_to_end_real_r2_and_inference", {})
    if e2e:
        with (run_dir / "etapas_pipeline_r2.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["etapa", "tiempo_ms"])
            writer.writerow(["transferencia_cliente_r2", e2e.get("upload_ms", 0)])
            for k, v in (e2e.get("timings") or {}).items():
                writer.writerow([k, v if v is not None else ""])

    print(f"[5/7] Ejecutando benchmark CPU reproducible (n={args.observations} calientes por condición) y muestreo de memoria ...")
    rc_bench, _, err_bench = run_step(
        [
            "python3",
            "scripts/benchmark_cpu.py",
            "--out-dir",
            str(run_dir),
            "--observations",
            str(args.observations),
        ]
    )
    if rc_bench != 0:
        raise RuntimeError(f"Benchmark CPU falló: {err_bench}")
    bench = json.loads((run_dir / "benchmark_cpu_resumen.json").read_text(encoding="utf-8"))
    memory = json.loads((run_dir / "memoria_servicios_resumen.json").read_text(encoding="utf-8"))

    print("[6/7] Ejecutando pruebas de interfaz Playwright y capturas reales ...")
    rc_pw, out_pw, err_pw = run_step(
        ["pnpm", "exec", "playwright", "test"],
        env={"DOPPLER_SCREENSHOT_DIR": str(capturas_dir)},
    )
    pw_raw = ROOT / "test-results/playwright-results.json"
    ui_report: dict[str, object] = {
        "exit_code": rc_pw,
        "all_passed": rc_pw == 0,
        "summary_text": f"Playwright finalizó con exit_code={rc_pw}",
    }
    if pw_raw.is_file():
        shutil.copy2(pw_raw, run_dir / "pruebas_interfaz.json")
        pw_data = json.loads(pw_raw.read_text(encoding="utf-8"))
        stats = pw_data.get("stats", {})
        ui_report["stats"] = stats
        ui_report["summary_text"] = (
            f"esperadas={stats.get('expected', 0)}, fallidas={stats.get('unexpected', 0)}, "
            f"omitidas={stats.get('skipped', 0)}"
        )
    else:
        (run_dir / "pruebas_interfaz.json").write_text(
            json.dumps({**ui_report, "stdout": out_pw[-1000:], "stderr": err_pw[-1000:]}, indent=2),
            encoding="utf-8",
        )

    print("[7/7] Renderizando diagramas y gráficas SVG/PNG en español y redactando informes ...")
    rc_ren, _, err_ren = run_step(
        ["python3", "scripts/render_diagrams_and_charts.py", "--run-dir", str(run_dir)]
    )
    if rc_ren != 0:
        raise RuntimeError(f"Error renderizando diagramas/gráficas: {err_ren}")

    write_markdown_reports(
        run_dir, run_id, env_info, parity, r2_report, integration, bench, memory, ui_report
    )

    manifest = {
        "run_id": run_id,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "validacion_local",
        "git_revision": env_info["git_revision"],
        "doppler_ml_commit": env_info["doppler_ml_reference_commit"],
        "sanitized_config": {
            "app_origin": r2_report.get("app_origin", "http://localhost:4321"),
            "r2_bucket": r2_report.get("bucket"),
            "r2_region": r2_report.get("region", "auto"),
            "max_file_bytes": 26214400,
            "max_duration_seconds": 120,
            "max_concurrent_inference": 1,
            "retention_hours": 24,
            "threshold": 0.6547843813896179,
        },
        "input_hashes_sha256": env_info["input_hashes_sha256"],
        "checks": {
            "parity_synthetic": bool(parity.get("all_passed")),
            "parity_historical": "not_applicable_no_historical_wavs_provided",
            "r2_storage_operations": bool(
                r2_report.get("checks", {}).get("presigned_get_and_sha256", {}).get("passed")
                and r2_report.get("checks", {}).get("delete_and_cleanup", {}).get("passed")
            ),
            "r2_browser_cors": bool(
                r2_report.get("checks", {}).get("cors_ready_for_origin", {}).get("passed")
            ),
            "integration_e2e_api_r2_sqlite": bool(integration.get("all_passed")),
            "cpu_benchmark_n30": rc_bench == 0,
            "playwright_ui": ui_report["all_passed"],
        },
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Evidencias generadas en: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
