#!/usr/bin/env python3
"""Motor de referencia, calibración y experimentos controlados de drift para Doppler (Capítulo 10.1).

Separa explícitamente:
  1. Partición de calibración (usada únicamente para construir la referencia congelada sintética
     y calibrar los umbrales de distancia Wasserstein 1D y cambio de proporciones mediante
     remuestreo bootstrap por archivo).
  2. Particiones de evaluación independientes (experimentos controlados con semillas distintas):
     - Exp 1: Referencia vs. grupo de control comparable (esperado: no_alert).
     - Exp 2: Población con cambios controlados de entrada y salida (esperado: drift_detected).
     - Exp 3: Muestra insuficiente por debajo de min_observations (esperado: insufficient_data).
     - Exp 4: Referencia ausente o incompatible (esperado: no_reference / evaluation_error).

Nota metodológica: al no existir un corpus de grabaciones reales en el repositorio, estos
experimentos demuestran técnicamente el detector sobre datos sintéticos identificados y
mantienen el estado operativo "referencia representativa pendiente" (synthetic_demo).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASELINE_MODEL_SHA = "e0dc2eaa1415f66d7442a8db7cf249129520ece20d575df35dc0aefb29f89d2a"
BASELINE_CONTRACT_SHA = "02b2a9884628a391cedfbf36803a775f85357fed05fb2549e3c01da157736557"


def wasserstein_1d(xs_in: list[float], ys_in: list[float]) -> float:
    xs = sorted(v for v in xs_in if math.isfinite(v))
    ys = sorted(v for v in ys_in if math.isfinite(v))
    if not xs or not ys:
        return 0.0
    pts = sorted(xs + ys)
    nx, ny = float(len(xs)), float(len(ys))
    i = j = 0
    area = 0.0
    for k in range(len(pts) - 1):
        left, right = pts[k], pts[k + 1]
        delta = right - left
        if delta <= 0.0:
            continue
        while i < len(xs) and xs[i] <= left:
            i += 1
        while j < len(ys) and ys[j] <= left:
            j += 1
        area += abs((i / nx) - (j / ny)) * delta
    return area


def max_abs_proportion_shift(ref_props: dict[str, float], obs_vals: list[str]) -> float:
    if not obs_vals:
        return 0.0
    counts: dict[str, int] = {}
    for v in obs_vals:
        counts[v] = counts.get(v, 0) + 1
    total = float(len(obs_vals))
    keys = set(ref_props.keys()) | set(counts.keys())
    return max(abs((counts.get(k, 0) / total) - ref_props.get(k, 0.0)) for k in keys)


def sample_synthetic_files(
    n_files: int,
    seed: int,
    *,
    sr_choices: list[tuple[str, float]],
    ch_choices: list[tuple[str, float]],
    dur_mean: float,
    dur_sd: float,
    peak_mean: float,
    peak_sd: float,
    rms_mean: float,
    rms_sd: float,
    silence_mean: float,
    clipping_mean: float,
    logmel_mean_center: float,
    centroid_center: float,
    pos_ratio_mean: float,
    score_mean_center: float,
    score_max_center: float,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)

    def pick_cat(choices: list[tuple[str, float]]) -> str:
        u = rng.random()
        acc = 0.0
        for label, prob in choices:
            acc += prob
            if u <= acc:
                return label
        return choices[-1][0]

    rows: list[dict[str, Any]] = []
    for i in range(n_files):
        dur = max(3.2, min(118.0, rng.gauss(dur_mean, dur_sd)))
        peak = max(0.02, min(1.0, rng.gauss(peak_mean, peak_sd)))
        rms = max(0.005, min(peak, rng.gauss(rms_mean, rms_sd)))
        sil = max(0.0, min(0.98, rng.gauss(silence_mean, 0.03)))
        clip = max(0.0, min(0.5, rng.gauss(clipping_mean, 0.004)))
        lm_mean = rng.gauss(logmel_mean_center, 3.2)
        lm_std = max(2.0, rng.gauss(12.5, 1.4))
        cent = max(180.0, min(7200.0, rng.gauss(centroid_center, 210.0)))
        pos_ratio = max(0.0, min(1.0, rng.gauss(pos_ratio_mean, 0.14)))
        sc_mean = max(0.01, min(0.99, rng.gauss(score_mean_center, 0.11)))
        sc_max = max(sc_mean, min(0.999, rng.gauss(score_max_center, 0.08)))
        rows.append(
            {
                "file_id": f"syn_{seed}_{i:03d}",
                "source_group": f"grp_{i % 6}",
                "original_sample_rate": pick_cat(sr_choices),
                "original_channels": pick_cat(ch_choices),
                "short_clip": "full",
                "duration_seconds": round(dur, 4),
                "peak_before_normalization": round(peak, 5),
                "rms_before_normalization": round(rms, 5),
                "silence_ratio": round(sil, 5),
                "clipping_ratio": round(clip, 5),
                "logmel_mean": round(lm_mean, 4),
                "logmel_std": round(lm_std, 4),
                "spectral_centroid_hz": round(cent, 2),
                "positive_window_ratio": round(pos_ratio, 4),
                "score_mean": round(sc_mean, 5),
                "score_max": round(sc_max, 5),
            }
        )
    return rows


def calibrate_thresholds_bootstrap(
    ref_rows: list[dict[str, Any]],
    numeric_fields: list[tuple[str, str, str]],
    cat_fields: list[str],
    sample_size: int,
    n_boot: int,
    seed: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Calibra umbrales por bootstrap sobre la partición de referencia (p99 × 1.25)."""
    rng = random.Random(seed)
    num_specs: dict[str, dict[str, Any]] = {}
    for field, group, unit in numeric_fields:
        vals = [float(r[field]) for r in ref_rows]
        scale = max(statistics.pstdev(vals), 1e-4)
        boot_d: list[float] = []
        for _ in range(n_boot):
            sub = [rng.choice(vals) for _ in range(sample_size)]
            boot_d.append(wasserstein_1d(vals, sub) / scale)
        boot_d.sort()
        p99 = boot_d[min(len(boot_d) - 1, int(0.99 * len(boot_d)))]
        thr = round(max(0.35, p99 * 1.25), 4)
        num_specs[field] = {
            "group": group,
            "unit": unit,
            "samples": vals,
            "scale": round(scale, 6),
            "bootstrap_p99_norm_w1": round(p99, 4),
            "threshold_normalized_w1": thr,
            "comparable": True,
            "note": f"Calibrado vía {n_boot} réplicas bootstrap (n={sample_size}, p99*1.25) sobre partición sintética de referencia.",
        }

    cat_specs: dict[str, dict[str, Any]] = {}
    for field in cat_fields:
        vals = [str(r[field]) for r in ref_rows]
        props: dict[str, float] = {}
        for v in vals:
            props[v] = props.get(v, 0.0) + 1.0 / len(vals)
        boot_s: list[float] = []
        for _ in range(n_boot):
            sub = [rng.choice(vals) for _ in range(sample_size)]
            boot_s.append(max_abs_proportion_shift(props, sub))
        boot_s.sort()
        p99 = boot_s[min(len(boot_s) - 1, int(0.99 * len(boot_s)))]
        thr = round(max(0.18, p99 * 1.25), 4)
        cat_specs[field] = {
            "proportions": {k: round(v, 6) for k, v in sorted(props.items())},
            "bootstrap_p99_shift": round(p99, 4),
            "threshold_max_abs_diff": thr,
            "comparable": True,
            "note": f"Calibrado vía {n_boot} réplicas bootstrap (n={sample_size}, p99*1.25).",
        }
    return num_specs, cat_specs


def evaluate_rows_against_reference(
    reference: dict[str, Any] | None,
    obs_rows: list[dict[str, Any]],
    *,
    active_model_sha: str = BASELINE_MODEL_SHA,
    active_extraction_version: str = "obs_v1",
) -> dict[str, Any]:
    if reference is None:
        return {
            "status": "no_reference",
            "representative_status": "pending_representative_corpus",
            "sample_count": len(obs_rows),
            "input_drift_detected": False,
            "output_drift_detected": False,
            "summary": "Sin referencia congelada disponible.",
            "features": [],
        }

    if reference.get("observation_unit") != "file":
        return {
            "status": "evaluation_error",
            "representative_status": reference.get("representative_status", "unknown"),
            "sample_count": len(obs_rows),
            "input_drift_detected": False,
            "output_drift_detected": False,
            "summary": "Unidad de observación incompatible (se requiere 'file').",
            "features": [],
        }

    if reference.get("extraction_version") != active_extraction_version:
        return {
            "status": "evaluation_error",
            "representative_status": reference.get("representative_status", "unknown"),
            "sample_count": len(obs_rows),
            "input_drift_detected": False,
            "output_drift_detected": False,
            "summary": f"Versión de extracción incompatible ({reference.get('extraction_version')} vs {active_extraction_version}).",
            "features": [],
        }

    if reference.get("model_sha256") and reference["model_sha256"] != active_model_sha:
        return {
            "status": "evaluation_error",
            "representative_status": reference.get("representative_status", "unknown"),
            "sample_count": len(obs_rows),
            "input_drift_detected": False,
            "output_drift_detected": False,
            "summary": "Hash de modelo incompatible entre referencia y ejecución activa.",
            "features": [],
        }

    min_obs = int(reference.get("min_observations", 20))
    if len(obs_rows) < min_obs:
        return {
            "status": "insufficient_data",
            "representative_status": reference.get("representative_status", "synthetic_demo"),
            "sample_count": len(obs_rows),
            "input_drift_detected": False,
            "output_drift_detected": False,
            "summary": f"Muestra insuficiente: {len(obs_rows)} archivos < mínimo {min_obs}.",
            "features": [],
        }

    features: list[dict[str, Any]] = []
    input_alert = False
    output_alert = False

    for group_key in ("input_numeric", "output_numeric"):
        for fname, spec in reference.get(group_key, {}).items():
            obs_vals = [float(r[fname]) for r in obs_rows if r.get(fname) is not None]
            raw_w1 = wasserstein_1d(spec["samples"], obs_vals)
            norm_w1 = raw_w1 / max(float(spec["scale"]), 1e-9)
            thr = float(spec["threshold_normalized_w1"])
            alerted = norm_w1 > thr
            if alerted:
                if group_key == "input_numeric":
                    input_alert = True
                else:
                    output_alert = True
            features.append(
                {
                    "feature": fname,
                    "group": group_key,
                    "unit": spec["unit"],
                    "method": "wasserstein_1d_normalized",
                    "n_ref": len(spec["samples"]),
                    "n_obs": len(obs_vals),
                    "statistic": round(raw_w1, 6),
                    "normalized_statistic": round(norm_w1, 4),
                    "threshold": thr,
                    "ref_mean": round(statistics.fmean(spec["samples"]), 4),
                    "obs_mean": round(statistics.fmean(obs_vals), 4) if obs_vals else None,
                    "alerted": alerted,
                    "status": "alert" if alerted else "ok",
                }
            )

    for fname, spec in reference.get("input_categorical", {}).items():
        obs_cats = [str(r[fname]) for r in obs_rows if r.get(fname) is not None]
        shift = max_abs_proportion_shift(spec["proportions"], obs_cats)
        thr = float(spec["threshold_max_abs_diff"])
        alerted = shift > thr
        if alerted:
            input_alert = True
        features.append(
            {
                "feature": fname,
                "group": "input_categorical",
                "unit": "proportion",
                "method": "max_abs_proportion_shift",
                "n_ref": len(spec["proportions"]),
                "n_obs": len(obs_cats),
                "statistic": round(shift, 4),
                "normalized_statistic": round(shift, 4),
                "threshold": thr,
                "ref_mean": None,
                "obs_mean": None,
                "alerted": alerted,
                "status": "alert" if alerted else "ok",
            }
        )

    status = "drift_detected" if (input_alert or output_alert) else "no_alert"
    return {
        "status": status,
        "representative_status": reference.get("representative_status", "synthetic_demo"),
        "sample_count": len(obs_rows),
        "input_drift_detected": input_alert,
        "output_drift_detected": output_alert,
        "summary": (
            f"Cambio detectado (entrada={input_alert}, salida={output_alert}) sobre {len(obs_rows)} archivos."
            if status == "drift_detected"
            else f"Sin alerta según criterio calibrado sobre {len(obs_rows)} archivos."
        ),
        "features": features,
    }


def build_reference_and_run_experiments(out_dir: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    base_params = dict(
        sr_choices=[("16000", 0.50), ("44100", 0.30), ("48000", 0.20)],
        ch_choices=[("1", 0.65), ("2", 0.35)],
        dur_mean=9.0,
        dur_sd=2.5,
        peak_mean=0.68,
        peak_sd=0.14,
        rms_mean=0.18,
        rms_sd=0.05,
        silence_mean=0.08,
        clipping_mean=0.002,
        logmel_mean_center=-36.0,
        centroid_center=1450.0,
        pos_ratio_mean=0.35,
        score_mean_center=0.42,
        score_max_center=0.72,
    )

    # Partición exclusiva de calibración (semilla 20261001, n=90 archivos, 6 grupos de origen)
    ref_rows = sample_synthetic_files(90, seed=20261001, **base_params)
    numeric_fields = [
        ("duration_seconds", "input_numeric", "s"),
        ("peak_before_normalization", "input_numeric", "amplitude"),
        ("rms_before_normalization", "input_numeric", "rms"),
        ("silence_ratio", "input_numeric", "ratio"),
        ("clipping_ratio", "input_numeric", "ratio"),
        ("logmel_mean", "input_numeric", "dB"),
        ("spectral_centroid_hz", "input_numeric", "Hz"),
        ("positive_window_ratio", "output_numeric", "ratio"),
        ("score_mean", "output_numeric", "sigmoid"),
        ("score_max", "output_numeric", "sigmoid"),
    ]
    cat_fields = ["original_sample_rate", "original_channels"]
    num_specs, cat_specs = calibrate_thresholds_bootstrap(
        ref_rows, numeric_fields, cat_fields, sample_size=30, n_boot=300, seed=20261002
    )

    reference_payload = {
        "id": "ref_synthetic_demo_v1",
        "version": "1.0.0-synthetic-demo",
        "name": "Referencia sintética de demostración técnica (corpus real pendiente)",
        "provenance": "Generada sintéticamente con scripts/drift_engine.py (seed=20261001, n=90 archivos, calibración bootstrap seed=20261002). No sustituye una referencia sobre grabaciones reales.",
        "observation_unit": "file",
        "file_count": len(ref_rows),
        "source_group_count": 6,
        "representative_status": "synthetic_demo",
        "extraction_version": "obs_v1",
        "model_sha256": BASELINE_MODEL_SHA,
        "contract_version": "1.0.0",
        "contract_sha256": BASELINE_CONTRACT_SHA,
        "min_observations": 20,
        "calibration_note": "Umbrales calibrados por bootstrap (300 réplicas, n=30, percentil 99 × 1,25) sobre partición de calibración separada de los experimentos.",
        "input_numeric": {
            k: {kk: vv for kk, vv in v.items() if kk != "group"}
            for k, v in num_specs.items()
            if v["group"] == "input_numeric"
        },
        "input_categorical": cat_specs,
        "output_numeric": {
            k: {kk: vv for kk, vv in v.items() if kk != "group"}
            for k, v in num_specs.items()
            if v["group"] == "output_numeric"
        },
    }

    # Experimentos independientes con semillas separadas
    control_rows = sample_synthetic_files(35, seed=20261011, **base_params)
    shifted_rows = sample_synthetic_files(
        35,
        seed=20261012,
        sr_choices=[("8000", 0.65), ("16000", 0.25), ("44100", 0.10)],
        ch_choices=[("1", 0.20), ("2", 0.80)],
        dur_mean=22.0,
        dur_sd=4.5,
        peak_mean=0.22,
        peak_sd=0.08,
        rms_mean=0.05,
        rms_sd=0.02,
        silence_mean=0.36,
        clipping_mean=0.045,
        logmel_mean_center=-50.5,
        centroid_center=2650.0,
        pos_ratio_mean=0.78,
        score_mean_center=0.76,
        score_max_center=0.94,
    )
    small_rows = sample_synthetic_files(8, seed=20261013, **base_params)

    exp1 = evaluate_rows_against_reference(reference_payload, control_rows)
    exp2 = evaluate_rows_against_reference(reference_payload, shifted_rows)
    exp3 = evaluate_rows_against_reference(reference_payload, small_rows)
    exp4_missing = evaluate_rows_against_reference(None, control_rows)
    exp4_incompat = evaluate_rows_against_reference(
        reference_payload, control_rows, active_model_sha="000000000000_model_v2_mismatch"
    )

    experiments = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "simulation_disclaimer": "Experimentos controlados sobre poblaciones sintéticas identificadas para demostrar el comportamiento del detector de drift. El estado operativo sobre tráfico real permanece como 'referencia representativa pendiente'.",
        "calibration": {
            "seed_reference": 20261001,
            "seed_bootstrap": 20261002,
            "reference_files": 90,
            "bootstrap_replicas": 300,
            "bootstrap_sample_size": 30,
            "rule": "max(min_floor, p99_bootstrap * 1.25)",
        },
        "experiments": [
            {
                "id": "exp_1_control_comparable",
                "description": "Referencia frente a grupo de control comparable independiente (n=35 archivos, seed=20261011).",
                "seed": 20261011,
                "expected_status": "no_alert",
                "passed": exp1["status"] == "no_alert",
                "result": exp1,
            },
            {
                "id": "exp_2_cambios_controlados",
                "description": "Población con cambios controlados de muestreo (8 kHz), canales, duración, silencio/saturación, centroide y salidas (n=35 archivos, seed=20261012).",
                "seed": 20261012,
                "expected_status": "drift_detected",
                "passed": (
                    exp2["status"] == "drift_detected"
                    and exp2["input_drift_detected"]
                    and exp2["output_drift_detected"]
                ),
                "result": exp2,
            },
            {
                "id": "exp_3_muestra_insuficiente",
                "description": "Muestra inferior al mínimo configurado de 20 archivos (n=8 archivos, seed=20261013).",
                "seed": 20261013,
                "expected_status": "insufficient_data",
                "passed": exp3["status"] == "insufficient_data",
                "result": exp3,
            },
            {
                "id": "exp_4a_referencia_ausente",
                "description": "Evaluación sin referencia congelada disponible.",
                "seed": None,
                "expected_status": "no_reference",
                "passed": exp4_missing["status"] == "no_reference",
                "result": exp4_missing,
            },
            {
                "id": "exp_4b_referencia_incompatible",
                "description": "Referencia con hash de modelo incompatible frente a la ejecución activa.",
                "seed": None,
                "expected_status": "evaluation_error",
                "passed": exp4_incompat["status"] == "evaluation_error",
                "result": exp4_incompat,
            },
        ],
    }
    experiments["all_passed"] = all(e["passed"] for e in experiments["experiments"])

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "referencia_drift.json").write_text(
            json.dumps(reference_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (out_dir / "experimentos_drift.json").write_text(
            json.dumps(experiments, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        # CSV complementario con comparación por característica de Exp 1 vs Exp 2
        csv_path = out_dir / "drift_comparacion_caracteristicas.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "experimento",
                    "caracteristica",
                    "grupo",
                    "metodo",
                    "n_ref",
                    "n_obs",
                    "estadistico",
                    "estadistico_normalizado",
                    "umbral",
                    "alerta",
                ]
            )
            for exp_id, res in [("exp_1_control", exp1), ("exp_2_cambio_controlado", exp2)]:
                for feat in res["features"]:
                    writer.writerow(
                        [
                            exp_id,
                            feat["feature"],
                            feat["group"],
                            feat["method"],
                            feat["n_ref"],
                            feat["n_obs"],
                            feat["statistic"],
                            feat["normalized_statistic"],
                            feat["threshold"],
                            feat["alerted"],
                        ]
                    )

    return reference_payload, experiments


def main() -> int:
    parser = argparse.ArgumentParser(description="Motor de referencia y experimentos de drift Doppler")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    _, exps = build_reference_and_run_experiments(args.out_dir)
    print(
        json.dumps(
            {
                "all_passed": exps["all_passed"],
                "results": [
                    {"id": e["id"], "status": e["result"]["status"], "passed": e["passed"]}
                    for e in exps["experiments"]
                ],
            },
            indent=2,
        )
    )
    return 0 if exps["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
