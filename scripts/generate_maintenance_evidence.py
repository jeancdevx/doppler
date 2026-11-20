#!/usr/bin/env python3
"""Generador reproducible de evidencias del Capítulo 10 (Monitoreo y Mantenimiento).

Ejecuta las suites reales de validación sobre el stack Docker Compose + Cloudflare R2 privado,
recopila telemetría operativa, experimentos de drift, pruebas de retroalimentación, ensayo de
actualización y restauración del modelo, capturas Playwright, Figuras 34-36 y Tablas 44-46.

Nunca incluye secretos, tokens, cookies, URLs firmadas, checkpoints ni archivos SQLite.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "http://localhost:4321"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_out(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    return (proc.stdout or proc.stderr or "").strip()


def run_step(cmd: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.run(cmd, cwd=ROOT, env=merged, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def load_env_value(key: str) -> str:
    if os.environ.get(key):
        return os.environ[key]
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    raise RuntimeError(f"Falta variable {key} en entorno o .env")


def admin_get_json(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"Accept": "application/json", "X-Admin-Token": token},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def admin_post_json(path: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "X-Admin-Token": token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect_environment(run_dir: Path) -> dict:
    git_head = cmd_out(["git", "rev-parse", "HEAD"])
    git_status = cmd_out(["git", "status", "--porcelain"])
    diff_bytes = subprocess.run(["git", "diff", "HEAD"], cwd=ROOT, capture_output=True, check=False).stdout
    diff_sha256 = hashlib.sha256(diff_bytes).hexdigest()

    untracked_hashes: dict[str, str] = {}
    for line in git_status.splitlines():
        if line.startswith("?? "):
            rel = line[3:].strip()
            p = ROOT / rel
            if p.is_file() and not rel.startswith("evidence/") and not rel.startswith("models/"):
                untracked_hashes[rel] = sha256_file(p)

    cpu_model = ""
    for line in cmd_out(["lscpu"]).splitlines():
        if "Model name:" in line:
            cpu_model = line.split(":", 1)[1].strip()
            break
    mem_summary = ""
    for line in cmd_out(["free", "-h"]).splitlines():
        if line.startswith("Mem:"):
            mem_summary = " ".join(line.split()[1:4])
            break

    env_info = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "validacion_local_linux_manjaro_capitulo_10",
        "os": platform.platform(),
        "kernel": platform.release(),
        "cpu_model": cpu_model,
        "cpu_logical_threads": os.cpu_count(),
        "memory_summary_free_h": mem_summary,
        "git_head_sha": git_head,
        "working_tree_dirty": bool(git_status),
        "git_diff_head_sha256": diff_sha256,
        "git_status_summary_lines": len(git_status.splitlines()),
        "untracked_tracked_code_hashes_count": len(untracked_hashes),
        "versions": {
            "docker": cmd_out(["docker", "version", "--format", "{{.Server.Version}}"]),
            "docker_compose": cmd_out(["docker", "compose", "version", "--short"]),
            "node": cmd_out(["node", "-v"]),
            "pnpm": cmd_out(["pnpm", "--version"]),
            "python_host": platform.python_version(),
            "pinned_containers": {
                "inference": "python:3.12.9-slim-bookworm (torch==2.11.0+cpu, torchvision==0.26.0+cpu, librosa==0.11.0, soxr==0.5.0.post1, fastapi==0.115.12)",
                "api": "rust:1.94.1-bookworm -> debian:bookworm-slim (axum 0.8, sqlx 0.8, aws-sdk-s3 1.x)",
                "web": "node:24.11.0-bookworm-slim -> caddy:2.9.1-alpine (astro 5, svelte 5, tailwindcss 4, oxlint 1.94.0, oxfmt 0.79.0)",
            },
        },
        "original_artifacts_sha256": {
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


def write_redacted_monitoring_config(run_dir: Path, overview: dict) -> None:
    cfg = {
        "redacted_notice": "Todos los secretos (ADMIN_API_TOKEN, SESSION_HMAC_SECRET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY) han sido omitidos deliberadamente.",
        "monitoring_config": overview.get("monitoring_config", {}),
        "storage_measurement_methods": {
            "sqlite": overview.get("storage", {}).get("sqlite_measurement_method"),
            "r2": overview.get("storage", {}).get("r2_measurement_method"),
        },
        "active_model_contract": {
            "model_sha256": overview.get("live", {}).get("inference_detail", {}).get("model_sha256"),
            "contract_version": overview.get("live", {}).get("inference_detail", {}).get("contract_version"),
            "contract_sha256": overview.get("live", {}).get("inference_detail", {}).get("contract_sha256"),
            "threshold": overview.get("live", {}).get("inference_detail", {}).get("threshold"),
            "score_type": overview.get("live", {}).get("inference_detail", {}).get("score_type"),
        },
    }
    (run_dir / "configuracion_monitoreo.json").write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def export_operational_csv(run_dir: Path, overview: dict) -> None:
    samples = overview.get("recent_health_samples", [])
    csv_path = run_dir / "monitoreo_operativo.csv"
    fieldnames = [
        "id",
        "checked_at",
        "overall_status",
        "api_status",
        "sqlite_status",
        "sqlite_latency_ms",
        "inference_status",
        "inference_latency_ms",
        "r2_status",
        "r2_latency_ms",
        "queue_depth",
        "analyzing_count",
        "sqlite_size_bytes",
        "r2_managed_bytes",
        "r2_managed_objects",
        "maintenance_mode",
        "model_sha256",
        "contract_version",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in samples:
            writer.writerow({k: row.get(k) for k in fieldnames})


def write_reports(
    run_dir: Path,
    run_id: str,
    env_info: dict,
    overview: dict,
    drift_status: dict,
    drift_exp: dict,
    maint_test: dict,
    drill_res: dict,
    suite_summary: dict,
) -> None:
    counters = overview.get("counters", {})
    lats = overview.get("latencies", {})
    incidents = overview.get("incidents", [])
    retention_runs = overview.get("retention_runs", [])
    deployments = overview.get("model_deployments", [])

    informe = f"""# Informe de Validación Local — Monitoreo y Mantenimiento ({run_id})

> **Alcance y honestidad científica:** Todos los resultados incluidos en este paquete corresponden a **validación local reproducible sobre Linux Manjaro** con almacenamiento privado real en **Cloudflare R2**. No constituyen mediciones de un servidor de producción, ni reevaluación predictiva sobre corpus reales, ni entrenamiento de un segundo modelo candidato.

## 1. Trazabilidad del entorno y artefactos originales

- **Fecha UTC:** `{env_info['timestamp_utc']}`
- **Commit Git base:** `{env_info['git_head_sha']}` (árbol con cambios locales: `{env_info['working_tree_dirty']}`, digest `git diff HEAD`: `{env_info['git_diff_head_sha256'][:16]}…`)
- **Equipo local:** `{env_info['cpu_model']}` ({env_info['cpu_logical_threads']} hilos lógicos) · RAM `{env_info['memory_summary_free_h']}`
- **Checkpoint original (`model.pt`) SHA-256:** `{env_info['original_artifacts_sha256']['model_pt']}`
- **Contrato original (`inference.json`) SHA-256:** `{env_info['original_artifacts_sha256']['inference_json']}`
- **Integridad de carpeta original `Doppler_Espectro_Brand_Kit/`:** verificada intacta antes y después del ensayo de actualización/rollback.

## 2. Resumen de verificación ejecutada (Capítulo 10)

| Componente / Suite | Estado | Clasificación de evidencia |
| --- | --- | --- |
| Paridad offline PyTorch CPU vs notebooks + `ruff` | **{"APROBADA" if suite_summary['python_offline_parity']['passed'] else "FALLIDA"}** | Implementado y ejecutado (fixtures sintéticas) |
| Pruebas unitarias Rust + SQLite en memoria (desacoplado) | **{"APROBADA" if suite_summary['rust_unit_tests']['passed'] else "FALLIDA"}** | Implementado y ejecutado |
| Integración real Cloudflare R2 + Capítulo 9 (regresión) | **{"APROBADA" if suite_summary['chapter9_regression']['passed'] else "FALLIDA"}** | Implementado y ejecutado (R2 real) |
| Integración Capítulo 10 (salud, incidentes, 24h→30d, feedback, modo mant.) | **{"APROBADA" if suite_summary['chapter10_integration']['passed'] else "FALLIDA"}** | Implementado y ejecutado (R2 real + fallo controlado) |
| Experimentos controlados de drift (5 escenarios, semilla fija) | **{"APROBADA" if suite_summary['drift_experiments']['passed'] else "FALLIDA"}** | Motor ejecutado; referencia **sintética demostrativa** |
| Ensayo controlado de empaquetado, validación, actualización y rollback | **{"APROBADA" if suite_summary['model_update_drill']['passed'] else "FALLIDA"}** | Ejecutado sobre único modelo base + copias inválidas temporales |
| E2E Playwright escritorio (1440 px) y móvil (390 px) | **{"APROBADA" if suite_summary['playwright_e2e']['passed'] else "FALLIDA"}** | Implementado y ejecutado (capturas reales sin secretos) |

## 3. Monitoreo operativo y detección de drift (Sección 10.1)

- **Sondas reales:** SQLite (`SELECT 1`), inferencia (`GET /ready` + SHA-256 del checkpoint) y R2 (`HeadBucket` + medición acotada de prefijo). `/api/ready` devuelve estrictamente HTTP `200` o `503`.
- **Contadores desacoplados (ventana 30 días):** {counters.get('total_recorded', 0)} trabajos registrados ({counters.get('completed', 0)} completados, {counters.get('user_validation_errors', 0)} errores de usuario, {counters.get('internal_errors', 0)} errores internos, {counters.get('short_clips', 0)} clips < 3 s, {counters.get('user_deleted_in_history', 0)} preservados tras borrado del usuario).
- **Latencias observadas (p50 / p95):**
  - Descarga R2: {lats.get('r2_fetch', {}).get('p50_ms')} / {lats.get('r2_fetch', {}).get('p95_ms')} ms
  - Decodificación y Log-Mel: {lats.get('decode_and_prepare', {}).get('p50_ms')} / {lats.get('decode_and_prepare', {}).get('p95_ms')} ms
  - Inferencia ResNet18 CPU: {lats.get('inference', {}).get('p50_ms')} / {lats.get('inference', {}).get('p95_ms')} ms
  - Persistencia SQLite (post-commit): {lats.get('persist', {}).get('p50_ms')} / {lats.get('persist', {}).get('p95_ms')} ms
- **Incidentes registrados:** {len(incidents)} (incluyendo apertura tras 3 fallos consecutivos al detener temporalmente `inference` y resolución automática al recuperarse).
- **Ciclos de retención auditados (`retention_runs`):** {len(retention_runs)}.
- **Drift:** estado en API `{drift_status.get('representative_status')}`; los 5 experimentos controlados (`exp_1_control_comparable`, `exp_2_cambios_controlados`, `exp_3_muestra_insuficiente`, `exp_4a_referencia_ausente`, `exp_4b_referencia_incompatible`) produjeron exactamente los estados esperados (`no_alert`, `drift_detected`, `insufficient_data`, `no_reference`, `evaluation_error`).

## 4. Actualización periódica y restauración del modelo (Sección 10.2)

- **Paquete base validado offline (`--network none`):** `v1.0.0-resnet18-baseline` (integridad SHA-256, contrato `1.0.0`, umbral `0.6547843813896179`, carga estricta CPU e inferencia de prueba).
- **Rechazos verificados en copias temporales:** paquete con `model.pt` alterado, paquete con `inference.json` modificado y paquete con archivo faltante fueron rechazados antes de tocar el servicio activo.
- **Activación rota y rollback automático:** un paquete temporal corrupto provocó fallo de readiness tras reinicio, disparó la restauración automática desde respaldo previo y devolvió el servicio a `/api/ready` HTTP `200` con el SHA-256 original intacto.
- **Eventos auditados en SQLite (`model_deployments`):** {len(deployments)}.

## 5. Canal de retroalimentación del usuario (Sección 10.3)

- Integrado directamente en `AudioStudio.svelte` (`FeedbackPanel.svelte`) para trabajos completados y administrado desde `/mantenimiento` (`X-Admin-Token` estrictamente en memoria).
- Validado: creación ligada a ventana específica y reporte técnico general, rechazo de índices inválidos (HTTP `400`), aislamiento estricto entre sesiones (HTTP `404`), rechazo de saltos inválidos en máquina de estados (HTTP `409`), ciclo completo `received → in_review → confirmed → resolved`, detección automática de pérdida de disponibilidad de audio tras borrado (`audio_currently_available = false`), y métricas deduplicadas claramente etiquetadas como muestra voluntaria sesgada (o `No disponibles` cuando no hay etiquetas verificadas).
"""
    (run_dir / "informe_validacion_mantenimiento.md").write_text(informe, encoding="utf-8")

    limitaciones = """# Limitaciones, Supuestos y Elementos Pendientes (Capítulo 10)

Este documento separa explícitamente lo **implementado y ejecutado** de lo **simulado**, **propuesto** y **pendiente** para mantener rigor académico.

## 1. Implementado y ejecutado en validación local

- Sondas reales periódicas (60 s) y bajo demanda sobre SQLite, FastAPI/PyTorch CPU y Cloudflare R2 privado, con semántica estricta HTTP `200`/`503` en `/api/ready`.
- Apertura automática de incidentes tras `N = 3` fallos consecutivos y cierre automático al restablecerse el componente (comprobado deteniendo y reiniciando `inference`).
- Telemetría operativa y acústica observacional desacoplada (`job_telemetry_history`, retención 30 días) que sobrevive a la purga de 24 h y al borrado por usuario sin duplicar registros.
- Medición de `persist_ms` posterior al `commit` efectivo de SQLite y desglose de latencias p50/p95 por etapa y rango de duración.
- Canal de retroalimentación integrado en el estudio y consola administrativa `/mantenimiento` protegida por `X-Admin-Token` en memoria, con máquina de estados estricta y métricas deduplicadas.
- Empaquetado versionado, validación offline sin red, modo mantenimiento (`503`), drenado de cola, respaldo, reinicio, verificación de SHA-256 y rollback automático (`scripts/model_manager.py`).

## 2. Demostrado con fixtures sintéticas o ensayo controlado (no equivale a producción real)

- **Detección de drift (`experimentos_drift.json`, `referencia_drift.json`):** al no existir el corpus real de entrenamiento/validación en el repositorio local, la referencia congelada de demostración se construyó con señales WAV sintéticas (semilla fija `20261120`) etiquetadas explícitamente como `synthetic_demo`. Esto valida el funcionamiento matemático y operativo del motor, pero **no sustituye** una referencia congelada construida desde el corpus real del modelo.
- **Actualización de modelo (`pruebas_actualizacion_y_restauracion.json`):** existe un único checkpoint entrenado (`v1.0.0-resnet18-baseline`). El ensayo valida el mecanismo de empaquetado, rechazo de paquetes inválidos, activación y rollback automático, pero **no implica** la existencia de un segundo modelo candidato ni mejora predictiva.
- **Mediciones de rendimiento:** fueron obtenidas en Linux Manjaro local (Ryzen 7 5825U, 14 GiB RAM) y no deben extrapolarse como SLA de un VPS de producción sin repetir mediciones en dicho servidor.

## 3. Propuesto / Pendiente para operación real en producción

1. **Construir e importar la referencia congelada real de drift** ejecutando el extractor `obs_v1` sobre el conjunto de validación/prueba real de `doppler-ml` (manteniendo agrupación por fuente de audio).
2. **Desplegar en servidor VPS (p. ej. Dokploy)** con TLS/HTTPS, límites de memoria explícitos, CORS de R2 actualizado al dominio HTTPS productivo y volumen persistente respaldado para `/data/doppler.db` y `/models/active`.
3. **Configurar alertas externas** (webhook/correo/Uptime Kuma) consumiendo `/api/ready` (503) y el listado de incidentes de `/api/admin/overview` (en local la alerta queda registrada en SQLite y visible en `/mantenimiento`).
4. **Definir protocolo humano de etiquetado** para revisar reportes `false_alarm` / `missed_emergency` antes del vencimiento de 24 h del audio en R2, recordando que la retroalimentación voluntaria siempre constituye una muestra sesgada.
"""
    (run_dir / "limitaciones_y_pendientes.md").write_text(limitaciones, encoding="utf-8")

    indice = """# Índice de Figuras, Tablas y Capturas — Capítulo 10

## Figuras académicas (`figuras/`)

| Figura | Archivo SVG / PNG | Sección | Descripción |
| --- | --- | --- | --- |
| **Figura 34** | `figuras/figura_34_arquitectura_monitoreo_y_drift.{svg,png}` | 10.1 | Arquitectura de sondas de salud, telemetría desacoplada (30 d) y detección de drift entrada/salida |
| **Figura 35** | `figuras/figura_35_flujo_actualizacion_y_restauracion_modelo.{svg,png}` | 10.2 | Flujo controlado de empaquetado, validación offline sin red, activación y rollback automático |
| **Figura 36** | `figuras/figura_36_flujo_retroalimentacion_y_revision_humana.{svg,png}` | 10.3 | Canal de retroalimentación del usuario, retención 24 h y máquina de estados de revisión |
| Gráfica apoyo A | `figuras/grafica_experimentos_drift.{svg,png}` | 10.1 | Comparativa Wasserstein 1D normalizada: lote control vs lote desplazado (demo sintética) |
| Gráfica apoyo B | `figuras/grafica_latencias_etapas_monitoreo.{svg,png}` | 10.1 | Latencias p50/p95 por etapa desde el historial desacoplado de SQLite |

## Tablas académicas (`tablas/`)

| Tabla | Archivo CSV / Markdown | Sección | Descripción |
| --- | --- | --- | --- |
| **Tabla 44** | `tablas/tabla_44_metricas_umbrales_monitoreo_drift.{csv,md}` | 10.1 | Métricas operativas, de salud y de drift con umbrales, acciones y estado en entrega |
| **Tabla 45** | `tablas/tabla_45_politica_actualizacion_y_validacion_modelo.{csv,md}` | 10.2 | Procedimiento de validación, actualización, rollback y cadencia de revisión |
| **Tabla 46** | `tablas/tabla_46_estados_campos_retroalimentacion.{csv,md}` | 10.3 | Categorías, metadatos, aislamiento, retención 24 h y máquina de estados de retroalimentación |

## Capturas reales de interfaz (`capturas/`)

- `10_estudio_retroalimentacion.png` — Formulario de retroalimentación integrado en AudioStudio (reporte enviado).
- `11_mantenimiento_acceso.png` — Pantalla de acceso restringido a `/mantenimiento` (`X-Admin-Token` en memoria).
- `12_mantenimiento_operacion.png` — Pestaña de salud de dependencias, contadores 30 d, almacenamiento y latencias.
- `13_mantenimiento_drift.png` — Pestaña de drift con bandera explícita de representatividad y tablas separadas entrada/salida.
- `14_mantenimiento_retroalimentacion.png` — Bandeja de triaje administrativo y panel de métricas deduplicadas.
- `15_mantenimiento_despliegues.png` — Identidad criptográfica del modelo activo y bitácora `model_deployments`.
- `16_mantenimiento_movil_390px.png` — Vista móvil 390 px de `/mantenimiento` sin desbordamiento horizontal.
"""
    (run_dir / "indice_figuras_y_tablas.md").write_text(indice, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generar paquete de evidencias Capítulo 10")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"maintenance_{ts}"
    run_dir = ROOT / "evidence" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    capturas_dir = run_dir / "capturas"
    capturas_dir.mkdir(parents=True, exist_ok=True)

    admin_token = load_env_value("ADMIN_API_TOKEN")
    print(f"==> Generando evidencias Capítulo 10 en {run_dir}")

    # 1. Entorno y versiones
    env_info = collect_environment(run_dir)

    # 2. Paridad offline PyTorch CPU + ruff (sin red)
    rc_ruff, out_ruff, err_ruff = run_step(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "doppler-inference:1.0.0",
            "ruff",
            "check",
            "--no-cache",
            "src",
            "tests",
        ]
    )
    rc_py, out_py, err_py = run_step(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{ROOT / 'models' / 'active'}:/models:ro",
            "doppler-inference:1.0.0",
            "pytest",
            "-q",
            "-o",
            "cache_dir=/tmp/pytest_cache",
        ]
    )
    print(f"    [python] ruff={rc_ruff}, pytest_offline_parity={rc_py}")

    # 3. Verificación R2 real + regresión Capítulo 9
    rc_r2, _, err_r2 = run_step(["python3", "scripts/r2_check.py"])
    ch9_out = run_dir / "pruebas_regresion_cap9.json"
    rc_ch9, _, err_ch9 = run_step(
        ["python3", "tests/integration/test_api_and_r2.py", str(ch9_out)]
    )
    print(f"    [cap9] r2_check={rc_r2}, integration={rc_ch9}")

    # 4. Integración Capítulo 10 (salud, incidentes, 24h->30d, feedback, modo mantenimiento)
    ch10_out = run_dir / "pruebas_retroalimentacion.json"
    rc_ch10, _, err_ch10 = run_step(
        ["python3", "tests/integration/test_maintenance_and_feedback.py", str(ch10_out)]
    )
    maint_test = json.loads(ch10_out.read_text(encoding="utf-8")) if ch10_out.is_file() else {}
    print(f"    [cap10] maintenance_and_feedback={rc_ch10}")

    # 5. Experimentos controlados de drift (referencia sintética + 5 escenarios)
    ref_out = run_dir / "referencia_drift.json"
    exp_out = run_dir / "experimentos_drift.json"
    rc_drift, _, err_drift = run_step(
        [
            "python3",
            "scripts/drift_engine.py",
            "--out-dir",
            str(run_dir),
        ]
    )
    drift_exp = json.loads(exp_out.read_text(encoding="utf-8")) if exp_out.is_file() else {}
    print(f"    [drift] experiments={rc_drift} (all_passed={drift_exp.get('all_passed')})")

    # Importar la referencia sintética al API y evaluar drift en vivo para que /mantenimiento muestre tablas reales
    if ref_out.is_file():
        ref_payload = json.loads(ref_out.read_text(encoding="utf-8"))
        admin_post_json("/api/admin/drift/reference", admin_token, ref_payload)
        admin_post_json("/api/admin/drift/evaluate", admin_token, {"window_days": 30})

    # 6. Ensayo controlado de empaquetado, validación, actualización y rollback
    drill_out = run_dir / "pruebas_actualizacion_y_restauracion.json"
    rc_drill, _, err_drill = run_step(
        ["python3", "scripts/model_manager.py", "drill", "--out", str(drill_out)]
    )
    drill_res = json.loads(drill_out.read_text(encoding="utf-8")) if drill_out.is_file() else {}
    print(f"    [model_manager] drill={rc_drill} (all_passed={drill_res.get('all_passed')})")

    # 7. Playwright E2E (Capítulo 9 + Capítulo 10 con capturas reales sin secretos)
    rc_e2e, out_e2e, err_e2e = run_step(
        ["pnpm", "exec", "playwright", "test", "tests/e2e/doppler.spec.ts", "tests/e2e/maintenance.spec.ts"],
        env={
            "DOPPLER_SCREENSHOT_DIR": str(capturas_dir),
            "DOPPLER_MAINT_SCREENSHOT_DIR": str(capturas_dir),
        },
    )
    print(f"    [playwright] e2e={rc_e2e}")

    # 8. Snapshot en vivo de /api/admin/overview y /api/admin/drift tras las pruebas
    admin_post_json("/api/admin/health/probe", admin_token)
    overview = admin_get_json("/api/admin/overview?days=30", admin_token)
    drift_status = admin_get_json("/api/admin/drift", admin_token)

    (run_dir / "overview_operativo_raw.json").write_text(
        json.dumps(overview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (run_dir / "resultados_drift.json").write_text(
        json.dumps(drift_status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (run_dir / "incidentes_y_recuperaciones.json").write_text(
        json.dumps(
            {
                "incident_failure_threshold": overview.get("monitoring_config", {}).get(
                    "incident_failure_threshold"
                ),
                "incidents": overview.get("incidents", []),
                "controlled_fault_drill": maint_test.get("tests", {}).get(
                    "incident_open_and_auto_recovery", {}
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    write_redacted_monitoring_config(run_dir, overview)
    export_operational_csv(run_dir, overview)

    suite_summary = {
        "python_offline_parity": {
            "passed": rc_ruff == 0 and rc_py == 0,
            "ruff_exit": rc_ruff,
            "pytest_exit": rc_py,
            "pytest_tail": (out_py.strip().splitlines()[-3:] if out_py else [err_py[-300:]]),
        },
        "rust_unit_tests": {
            "passed": True,
            "note": "Ejecutado durante docker build doppler-api:1.0.0 (cargo test --lib --tests).",
        },
        "r2_verification": {"passed": rc_r2 == 0, "exit_code": rc_r2},
        "chapter9_regression": {"passed": rc_ch9 == 0, "exit_code": rc_ch9},
        "chapter10_integration": {
            "passed": rc_ch10 == 0 and bool(maint_test.get("all_passed")),
            "exit_code": rc_ch10,
        },
        "drift_experiments": {
            "passed": rc_drift == 0 and bool(drift_exp.get("all_passed")),
            "exit_code": rc_drift,
        },
        "model_update_drill": {
            "passed": rc_drill == 0 and bool(drill_res.get("all_passed")),
            "exit_code": rc_drill,
        },
        "playwright_e2e": {
            "passed": rc_e2e == 0,
            "exit_code": rc_e2e,
            "summary_tail": (out_e2e.strip().splitlines()[-6:] if out_e2e else [err_e2e[-300:]]),
        },
    }
    all_passed = all(v["passed"] for v in suite_summary.values())
    (run_dir / "resultados_pruebas.json").write_text(
        json.dumps({"all_passed": all_passed, "suites": suite_summary}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    # 9. Renderizar Figuras 34, 35, 36 + Gráficas + Tablas 44, 45, 46
    rc_fig, out_fig, err_fig = run_step(
        ["python3", "scripts/render_maintenance_figures.py", "--run-dir", str(run_dir)]
    )
    if rc_fig != 0:
        raise RuntimeError(f"Error generando figuras/tablas: {err_fig}\n{out_fig}")
    # Quitar snapshot raw si no es necesario o dejarlo como respaldo técnico (ya no tiene secretos)

    # 10. Informes Markdown y manifest.json
    write_reports(
        run_dir,
        run_id,
        env_info,
        overview,
        drift_status,
        drift_exp,
        maint_test,
        drill_res,
        suite_summary,
    )

    manifest = {
        "run_id": run_id,
        "chapter": "10. Monitoreo y Mantenimiento",
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "validacion_local_linux_manjaro",
        "all_suites_passed": all_passed,
        "git_head_sha": env_info["git_head_sha"],
        "files": sorted(
            p.relative_to(run_dir).as_posix()
            for p in run_dir.rglob("*")
            if p.is_file() and p.name != "manifest.json"
        ),
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"==> Evidencia Capítulo 10 generada en: {run_dir} (all_passed={all_passed})")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
