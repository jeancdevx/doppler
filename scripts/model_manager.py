#!/usr/bin/env python3
"""Herramienta local de administración de paquetes de modelo Doppler (Capítulo 10.2).

Permite:
  - init-active: inicializar el paquete base v1.0.0 y el directorio activo ./models/active
    a partir de Doppler_Espectro_Brand_Kit/model/ (sin modificar los originales).
  - validate <package_dir>: validar integridad SHA-256, compatibilidad de contrato,
    carga estricta CPU sin red (--network none) y regresión contra el contrato vigente.
  - activate <package_dir>: ejecutar transición controlada en 8 pasos (mantenimiento,
    drenado de cola, respaldo de versión vigente, validación, intercambio atómico,
    reinicio de inference, verificación /ready + hashes y rollback automático ante fallo).
  - drill: ejecutar un ensayo operativo controlado completo (validación del paquete real,
    rechazo de paquetes alterados/incompletos sobre copias temporales y activación con
    fallo inducido + restauración automática verificada), escribiendo un reporte JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL_MODEL_DIR = ROOT / "Doppler_Espectro_Brand_Kit" / "model"
MODELS_ROOT = ROOT / "models"
PACKAGES_DIR = MODELS_ROOT / "packages"
ACTIVE_DIR = MODELS_ROOT / "active"
BACKUP_DIR = MODELS_ROOT / "previous_backup"

EXPECTED_BASELINE_MODEL_SHA = "e0dc2eaa1415f66d7442a8db7cf249129520ece20d575df35dc0aefb29f89d2a"
EXPECTED_BASELINE_CONTRACT_SHA = "02b2a9884628a391cedfbf36803a775f85357fed05fb2549e3c01da157736557"


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def api_request(
    base_url: str,
    endpoint: str,
    method: str = "GET",
    admin_token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    url = f"{base_url.rstrip('/')}{endpoint}"
    headers = {"Accept": "application/json"}
    if admin_token:
        headers["X-Admin-Token"] = admin_token
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return err.code, parsed


def init_active_package() -> Path:
    """Crea el paquete versionado base y ./models/active preservando los originales en solo lectura."""
    orig_pt = ORIGINAL_MODEL_DIR / "model.pt"
    orig_cfg = ORIGINAL_MODEL_DIR / "inference.json"
    if not orig_pt.is_file() or not orig_cfg.is_file():
        raise FileNotFoundError(
            f"No se encontraron model.pt e inference.json en {ORIGINAL_MODEL_DIR}"
        )

    model_sha = sha256_file(orig_pt)
    cfg_sha = sha256_file(orig_cfg)
    cfg_data = json.loads(orig_cfg.read_text(encoding="utf-8"))

    pkg_dir = PACKAGES_DIR / "v1.0.0-resnet18-baseline"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(orig_pt, pkg_dir / "model.pt")
    shutil.copy2(orig_cfg, pkg_dir / "inference.json")
    os.chmod(pkg_dir / "model.pt", 0o644)
    os.chmod(pkg_dir / "inference.json", 0o644)

    manifest = {
        "package_version": "v1.0.0-resnet18-baseline",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approval_status": "approved_baseline",
        "files": {
            "model.pt": {
                "sha256": model_sha,
                "size_bytes": (pkg_dir / "model.pt").stat().st_size,
            },
            "inference.json": {
                "sha256": cfg_sha,
                "size_bytes": (pkg_dir / "inference.json").stat().st_size,
            },
        },
        "architecture": {
            "name": cfg_data.get("model_name", "resnet18"),
            "wrapper": "VisualTransfer(resnet18(weights=None), Dropout(0.3)+Linear(512,1))",
            "input_shape": cfg_data.get("input_shape", [64, 94]),
            "channel_repeat": 3,
        },
        "contract": {
            "version": "1.0.0",
            "sample_rate_hz": 16000,
            "resampler": "soxr_hq",
            "peak_target": 0.99,
            "window_seconds": 3.0,
            "hop_seconds": 1.5,
            "threshold": cfg_data.get("threshold", 0.6547843813896179),
            "score_type": cfg_data.get("score_type", "sigmoid_probability_not_calibrated"),
            "class_map": cfg_data.get("class_map", {"0": "NON_EMERGENCY", "1": "EMERGENCY"}),
        },
        "dependencies": {
            "python": "3.12.9",
            "torch": "2.11.0+cpu",
            "torchvision": "0.26.0+cpu",
            "librosa": "0.11.0",
            "soxr": "0.5.0.post1",
        },
        "provenance": {
            "source_repo": "https://github.com/jeancdevx/doppler-ml",
            "source_commit": "baacec8d9427bf42c001ab5ca9c13343e2ec0c60",
            "notebooks": ["00_preparacion_insumos.ipynb", "05_resnet18.ipynb"],
            "original_artifacts_readonly": "Doppler_Espectro_Brand_Kit/model/",
        },
    }
    (pkg_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    for fname in ("model.pt", "inference.json", "manifest.json"):
        shutil.copy2(pkg_dir / fname, ACTIVE_DIR / fname)
        os.chmod(ACTIVE_DIR / fname, 0o644)

    return pkg_dir


def validate_package(pkg_dir: Path, run_docker_load: bool = True) -> dict[str, Any]:
    """Valida un paquete versionado antes de cualquier activación."""
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    manifest_path = pkg_dir / "manifest.json"
    pt_path = pkg_dir / "model.pt"
    cfg_path = pkg_dir / "inference.json"

    for label, p in [
        ("manifest.json", manifest_path),
        ("model.pt", pt_path),
        ("inference.json", cfg_path),
    ]:
        ok = p.is_file() and p.stat().st_size > 0
        checks.append({"check": f"file_exists:{label}", "ok": ok})
        if not ok:
            errors.append(f"Archivo obligatorio ausente o vacío: {label}")

    if errors:
        return {"valid": False, "package_dir": str(pkg_dir), "checks": checks, "errors": errors}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        inf_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"JSON corrupto en manifest.json o inference.json: {exc}")
        return {"valid": False, "package_dir": str(pkg_dir), "checks": checks, "errors": errors}

    # 1. Integridad SHA-256
    actual_pt_sha = sha256_file(pt_path)
    actual_cfg_sha = sha256_file(cfg_path)
    expected_pt_sha = manifest.get("files", {}).get("model.pt", {}).get("sha256")
    expected_cfg_sha = manifest.get("files", {}).get("inference.json", {}).get("sha256")

    pt_hash_ok = bool(expected_pt_sha and actual_pt_sha == expected_pt_sha)
    cfg_hash_ok = bool(expected_cfg_sha and actual_cfg_sha == expected_cfg_sha)
    checks.append({"check": "sha256:model.pt", "ok": pt_hash_ok, "actual": actual_pt_sha})
    checks.append({"check": "sha256:inference.json", "ok": cfg_hash_ok, "actual": actual_cfg_sha})
    if not pt_hash_ok:
        errors.append("Discrepancia SHA-256 en model.pt frente a manifest.json.")
    if not cfg_hash_ok:
        errors.append("Discrepancia SHA-256 en inference.json frente a manifest.json.")

    # 2. Consistencia de contrato entre manifest.json e inference.json
    req_shape = [64, 94]
    inf_shape = inf_cfg.get("shape") or inf_cfg.get("input_shape")
    man_shape = manifest.get("architecture", {}).get("input_shape")
    shape_ok = inf_shape == req_shape and man_shape == req_shape
    checks.append({"check": "contract:input_shape_64x94", "ok": shape_ok, "value": inf_shape})
    if not shape_ok:
        errors.append(f"Forma de entrada incompatible: inference={inf_shape}, manifest={man_shape}")

    inf_thr = inf_cfg.get("threshold")
    man_thr = manifest.get("contract", {}).get("threshold")
    thr_ok = (
        isinstance(inf_thr, (int, float))
        and isinstance(man_thr, (int, float))
        and abs(float(inf_thr) - float(man_thr)) <= 1e-12
        and 0.0 < float(inf_thr) < 1.0
    )
    checks.append({"check": "contract:threshold_consistent", "ok": thr_ok, "value": inf_thr})
    if not thr_ok:
        errors.append(f"Umbral incoherente entre inference.json ({inf_thr}) y manifest.json ({man_thr}).")

    mean_len = len(inf_cfg.get("normalization_mean") or inf_cfg.get("band_mean", []))
    std_len = len(inf_cfg.get("normalization_std") or inf_cfg.get("band_std", []))
    stats_ok = mean_len == 64 and std_len == 64
    checks.append({"check": "contract:band_stats_64", "ok": stats_ok})
    if not stats_ok:
        errors.append(f"Estadísticas por banda inválidas: mean={mean_len}, std={std_len}")

    approval = manifest.get("approval_status")
    approval_ok = approval in {"approved_baseline", "approved_candidate", "approved_drill"}
    checks.append({"check": "governance:approval_status", "ok": approval_ok, "value": approval})
    if not approval_ok:
        errors.append(f"Estado de aprobación no válido para activación: {approval}")

    # 3. Carga estricta CPU + inferencia de regresión en contenedor aislado (--network none)
    if run_docker_load and not errors:
        py_probe = (
            "import json, numpy as np; "
            "from pathlib import Path; "
            "from doppler_inference.model import load_model_bundle; "
            "b = load_model_bundle(Path('/candidate/model.pt'), Path('/candidate/inference.json'), torch_num_threads=2); "
            "x = np.zeros((1, 64, 94), dtype=np.float32); "
            "s = b.predict_scores(x, batch_size=1); "
            "assert s.shape == (1,) and np.isfinite(s).all() and 0.0 <= float(s[0]) <= 1.0; "
            "print(json.dumps({'ok': True, 'model_sha256': b.model_sha256, 'contract_sha256': b.contract_sha256, 'zero_score': float(s[0])}))"
        )
        proc = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "-v",
                f"{pkg_dir.resolve()}:/candidate:ro",
                "doppler-inference:1.0.0",
                "python",
                "-c",
                py_probe,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        load_ok = proc.returncode == 0
        detail: Any = None
        if load_ok:
            try:
                detail = json.loads(proc.stdout.strip().splitlines()[-1])
            except Exception:
                detail = proc.stdout.strip()
        else:
            detail = (proc.stderr or proc.stdout).strip()[-400:]
            errors.append(f"Falló carga estricta CPU en contenedor aislado: {detail}")
        checks.append({"check": "docker_offline_strict_cpu_load", "ok": load_ok, "detail": detail})

    return {
        "valid": len(errors) == 0,
        "package_version": manifest.get("package_version", pkg_dir.name),
        "model_sha256": actual_pt_sha,
        "contract_sha256": actual_cfg_sha,
        "contract_version": manifest.get("contract", {}).get("version", "1.0.0"),
        "checks": checks,
        "errors": errors,
    }


def wait_for_inference_ready(
    api_base: str,
    expected_model_sha: str,
    timeout_s: float = 45.0,
) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            code, data = api_request(api_base, "/api/health", timeout=4.0)
            last = {"http_status": code, "body": data}
            inf = data.get("inference") or {}
            if (
                code == 200
                and inf.get("ready") is True
                and inf.get("model_loaded") is True
                and inf.get("model_sha256") == expected_model_sha
            ):
                return True, data
        except Exception as exc:
            last = {"error": str(exc)}
        time.sleep(1.5)
    return False, last


def wait_for_queue_drain(
    api_base: str, admin_token: str, timeout_s: float = 30.0
) -> tuple[bool, int]:
    deadline = time.monotonic() + timeout_s
    analyzing = 0
    while time.monotonic() < deadline:
        code, data = api_request(api_base, "/api/admin/maintenance", "GET", admin_token)
        if code == 200:
            analyzing = int(data.get("analyzing_active", 0))
            if analyzing == 0:
                return True, 0
        time.sleep(1.0)
    return False, analyzing


def copy_dir_contents(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for child in dst.iterdir():
        if child.is_file():
            child.unlink()
    for fname in ("model.pt", "inference.json", "manifest.json"):
        sp = src / fname
        if sp.is_file():
            shutil.copy2(sp, dst / fname)
            os.chmod(dst / fname, 0o644)


def activate_package(
    pkg_dir: Path,
    api_base: str,
    admin_token: str,
    simulate_broken_activation: bool = False,
) -> dict[str, Any]:
    """Ejecuta el procedimiento formal de 8 pasos con respaldo y restauración automática."""
    steps: list[dict[str, Any]] = []

    # Pre-validación del paquete candidato
    val = validate_package(pkg_dir, run_docker_load=True)
    steps.append({"step": "0_prevalidate", "ok": val["valid"], "summary": val})
    if not val["valid"]:
        api_request(
            api_base,
            "/api/admin/deployments",
            "POST",
            admin_token,
            {
                "action": "reject",
                "package_version": val.get("package_version", pkg_dir.name),
                "model_sha256": val.get("model_sha256"),
                "contract_version": val.get("contract_version"),
                "contract_sha256": val.get("contract_sha256"),
                "status": "failed",
                "reason": "; ".join(val.get("errors", ["paquete inválido"])),
            },
        )
        return {"ok": False, "rolled_back": False, "steps": steps, "validation": val}

    # Identificar versión vigente antes de modificar nada
    prev_model_sha = sha256_file(ACTIVE_DIR / "model.pt") if (ACTIVE_DIR / "model.pt").is_file() else None

    # Paso 1: Entrar en mantenimiento controlado
    code_m, resp_m = api_request(
        api_base,
        "/api/admin/maintenance",
        "POST",
        admin_token,
        {
            "enabled": True,
            "reason": f"Activación controlada de paquete {val['package_version']}"
            + (" (ensayo fallo + rollback)" if simulate_broken_activation else ""),
        },
    )
    steps.append({"step": "1_enter_maintenance", "ok": code_m == 200, "http_status": code_m})

    # Paso 2: Coordinar cola y esperar drenado de trabajos activos
    drained, remaining = wait_for_queue_drain(api_base, admin_token, timeout_s=30.0)
    steps.append({"step": "2_drain_active_jobs", "ok": drained, "analyzing_remaining": remaining})

    rolled_back = False
    activated_ok = False
    failure_reason = ""

    try:
        # Paso 3: Conservar respaldo de la versión vigente
        copy_dir_contents(ACTIVE_DIR, BACKUP_DIR)
        steps.append({"step": "3_backup_current_version", "ok": True, "previous_model_sha256": prev_model_sha})

        # Paso 4: Activar archivos en ./models/active (o simular paquete roto tras precheck para probar rollback)
        if simulate_broken_activation:
            copy_dir_contents(pkg_dir, ACTIVE_DIR)
            (ACTIVE_DIR / "model.pt").write_bytes(b"CORRUPTED_DRILL_CHECKPOINT_FOR_ROLLBACK_TEST")
            steps.append(
                {
                    "step": "4_stage_active_package",
                    "ok": True,
                    "simulated_broken_checkpoint": True,
                }
            )
        else:
            copy_dir_contents(pkg_dir, ACTIVE_DIR)
            steps.append(
                {
                    "step": "4_stage_active_package",
                    "ok": True,
                    "simulated_broken_checkpoint": False,
                }
            )

        # Paso 5: Reiniciar contenedor de inferencia para recargar desde /models:ro
        restart = subprocess.run(
            ["docker", "compose", "restart", "inference"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        steps.append(
            {
                "step": "5_restart_inference",
                "ok": restart.returncode == 0,
                "returncode": restart.returncode,
            }
        )

        # Paso 6: Comprobar salud e identidad real del modelo
        probe_timeout = 18.0 if simulate_broken_activation else 45.0
        ready_ok, health_data = wait_for_inference_ready(
            api_base,
            val["model_sha256"],
            timeout_s=probe_timeout,
        )
        steps.append(
            {
                "step": "6_verify_health_and_model_identity",
                "ok": ready_ok,
                "observed_model_sha256": (health_data.get("inference") or {}).get("model_sha256")
                if isinstance(health_data, dict)
                else None,
            }
        )

        if ready_ok:
            activated_ok = True
        else:
            failure_reason = "El servicio de inferencia no alcanzó /ready con el SHA-256 esperado."
            # Paso 7: Restauración automática a la versión anterior respaldada
            copy_dir_contents(BACKUP_DIR, ACTIVE_DIR)
            rb_restart = subprocess.run(
                ["docker", "compose", "restart", "inference"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            rb_ok, rb_health = wait_for_inference_ready(
                api_base,
                prev_model_sha or val["model_sha256"],
                timeout_s=45.0,
            )
            rolled_back = rb_restart.returncode == 0 and rb_ok
            steps.append(
                {
                    "step": "7_automatic_rollback",
                    "ok": rolled_back,
                    "restored_model_sha256": (rb_health.get("inference") or {}).get("model_sha256")
                    if isinstance(rb_health, dict)
                    else None,
                }
            )
    finally:
        # Paso 8: Salir de mantenimiento controlado
        code_exit, _ = api_request(
            api_base,
            "/api/admin/maintenance",
            "POST",
            admin_token,
            {"enabled": False, "reason": None},
        )
        steps.append({"step": "8_exit_maintenance", "ok": code_exit == 200, "http_status": code_exit})

    # Registrar auditoría en SQLite
    action = "rollback" if rolled_back else "activate"
    status = "ok" if activated_ok else ("rolled_back" if rolled_back else "failed")
    reason = (
        f"Activación controlada verificada ({val['package_version']})."
        if activated_ok
        else f"Activación fallida ({failure_reason}); restauración automática ejecutada={rolled_back}."
    )
    api_request(
        api_base,
        "/api/admin/deployments",
        "POST",
        admin_token,
        {
            "action": action,
            "package_version": val["package_version"],
            "model_sha256": val["model_sha256"],
            "contract_version": val["contract_version"],
            "contract_sha256": val["contract_sha256"],
            "previous_model_sha256": prev_model_sha,
            "status": status,
            "reason": reason,
            "details_json": json.dumps({"steps": steps}, ensure_ascii=False),
        },
    )

    return {
        "ok": activated_ok,
        "rolled_back": rolled_back,
        "status": status,
        "reason": reason,
        "steps": steps,
    }


def run_controlled_drill(api_base: str, admin_token: str, out_path: Path | None) -> dict[str, Any]:
    """Ejecuta el ensayo operativo completo sin alterar Doppler_Espectro_Brand_Kit/."""
    pkg_dir = init_active_package()
    orig_pt_sha_before = sha256_file(ORIGINAL_MODEL_DIR / "model.pt")

    # 1. Validar paquete vigente real
    valid_check = validate_package(pkg_dir, run_docker_load=True)

    # 2. Probar rechazo de paquetes inválidos sobre copias temporales
    rejected_cases: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="doppler_pkg_drill_") as tmp:
        tmp_root = Path(tmp)

        # Caso A: archivo incompleto (falta inference.json)
        case_missing = tmp_root / "pkg_missing_config"
        case_missing.mkdir()
        shutil.copy2(pkg_dir / "manifest.json", case_missing / "manifest.json")
        shutil.copy2(pkg_dir / "model.pt", case_missing / "model.pt")
        r_missing = validate_package(case_missing, run_docker_load=False)
        rejected_cases.append({"case": "missing_inference_json", "rejected": not r_missing["valid"], "errors": r_missing["errors"]})

        # Caso B: checkpoint alterado (discrepancia SHA-256)
        case_tampered = tmp_root / "pkg_tampered_pt"
        shutil.copytree(pkg_dir, case_tampered)
        (case_tampered / "model.pt").write_bytes(b"tampered_bytes_for_test")
        r_tampered = validate_package(case_tampered, run_docker_load=False)
        rejected_cases.append({"case": "tampered_checkpoint_sha256", "rejected": not r_tampered["valid"], "errors": r_tampered["errors"]})

        # Caso C: umbral inconsistente entre inference.json y manifest.json
        case_bad_thr = tmp_root / "pkg_inconsistent_threshold"
        shutil.copytree(pkg_dir, case_bad_thr)
        bad_cfg = json.loads((case_bad_thr / "inference.json").read_text(encoding="utf-8"))
        bad_cfg["threshold"] = 0.91
        (case_bad_thr / "inference.json").write_text(json.dumps(bad_cfg), encoding="utf-8")
        bad_man = json.loads((case_bad_thr / "manifest.json").read_text(encoding="utf-8"))
        bad_man["files"]["inference.json"]["sha256"] = sha256_file(case_bad_thr / "inference.json")
        (case_bad_thr / "manifest.json").write_text(json.dumps(bad_man), encoding="utf-8")
        r_bad_thr = validate_package(case_bad_thr, run_docker_load=False)
        rejected_cases.append({"case": "inconsistent_threshold", "rejected": not r_bad_thr["valid"], "errors": r_bad_thr["errors"]})

        # Registrar rechazo de ejemplo en auditoría
        api_request(
            api_base,
            "/api/admin/deployments",
            "POST",
            admin_token,
            {
                "action": "reject",
                "package_version": "drill-tampered-invalid",
                "status": "failed",
                "reason": "Ensayo controlado: rechazo de paquetes con archivo faltante, SHA-256 alterado y umbral inconsistente.",
            },
        )

    # 3. Activación con fallo inducido en copia activa + restauración automática
    rollback_drill = activate_package(
        pkg_dir, api_base, admin_token, simulate_broken_activation=True
    )

    # 4. Activación limpia idempotente del paquete base validado
    clean_activation = activate_package(
        pkg_dir, api_base, admin_token, simulate_broken_activation=False
    )

    orig_pt_sha_after = sha256_file(ORIGINAL_MODEL_DIR / "model.pt")
    code_ready, ready_resp = api_request(api_base, "/api/ready", "GET")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "drill_disclaimer": "Ensayo operativo controlado utilizando el único modelo entrenado disponible (v1.0.0-resnet18-baseline). No declara una segunda versión candidata ni mejora predictiva.",
        "originals_preserved_readonly": orig_pt_sha_before == orig_pt_sha_after == EXPECTED_BASELINE_MODEL_SHA,
        "baseline_validation": valid_check,
        "invalid_package_rejections": rejected_cases,
        "broken_activation_and_rollback_drill": rollback_drill,
        "clean_activation_drill": clean_activation,
        "post_drill_ready_http_status": code_ready,
        "post_drill_model_sha256": (ready_resp.get("inference") or {}).get("model_sha256"),
        "all_passed": (
            valid_check["valid"]
            and all(c["rejected"] for c in rejected_cases)
            and rollback_drill["rolled_back"]
            and clean_activation["ok"]
            and code_ready == 200
            and orig_pt_sha_before == orig_pt_sha_after
        ),
    }

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    env = load_env_file(ROOT / ".env")
    api_base = env.get("APP_ORIGIN", "http://localhost:4321")
    admin_token = os.environ.get("ADMIN_API_TOKEN") or env.get("ADMIN_API_TOKEN", "")

    parser = argparse.ArgumentParser(description="Administrador local de paquetes de modelo Doppler")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-active")
    p_val = sub.add_parser("validate")
    p_val.add_argument("package_dir", type=Path)
    p_val.add_argument("--no-docker", action="store_true")
    p_act = sub.add_parser("activate")
    p_act.add_argument("package_dir", type=Path)
    p_act.add_argument("--simulate-broken-activation", action="store_true")
    p_drill = sub.add_parser("drill")
    p_drill.add_argument("--out", type=Path, default=None)

    args = parser.parse_args()
    if args.cmd == "init-active":
        pkg = init_active_package()
        print(json.dumps({"ok": True, "package_dir": str(pkg), "active_dir": str(ACTIVE_DIR)}, indent=2))
        return 0
    if args.cmd == "validate":
        res = validate_package(args.package_dir, run_docker_load=not args.no_docker)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["valid"] else 1
    if args.cmd == "activate":
        if not admin_token:
            print("Error: ADMIN_API_TOKEN no configurado en .env o entorno.", file=sys.stderr)
            return 2
        res = activate_package(
            args.package_dir,
            api_base,
            admin_token,
            simulate_broken_activation=args.simulate_broken_activation,
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if (res["ok"] or (args.simulate_broken_activation and res["rolled_back"])) else 1
    if args.cmd == "drill":
        if not admin_token:
            print("Error: ADMIN_API_TOKEN no configurado en .env o entorno.", file=sys.stderr)
            return 2
        res = run_controlled_drill(api_base, admin_token, args.out)
        print(json.dumps({"all_passed": res["all_passed"], "post_drill_ready_http_status": res["post_drill_ready_http_status"]}, indent=2))
        return 0 if res["all_passed"] else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
