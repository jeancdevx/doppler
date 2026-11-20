#!/usr/bin/env python3
"""Benchmark CPU reproducible y muestreo explícito de memoria de Doppler (validación local).

- Separa arranque/carga inicial del modelo, calentamiento (warmup) y mediciones calientes.
- Ejecuta n >= 30 observaciones calientes por cada duración documentada (3 s, 6 s, 15 s, 30 s).
- Muestrea memoria de contenedores Docker (`docker stats --no-stream`) a frecuencia explícita (1 Hz)
  en reposo y bajo carga.
- Usa fixtures WAV sintéticas reproducibles (identificadas explícitamente como sintéticas).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
import os
import platform
import statistics
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

INFERENCE_URL = os.environ.get("INFERENCE_DEBUG_URL", "http://127.0.0.1:18090")


def synth_wav_pcm16(duration_s: float, sr: int = 16000) -> bytes:
    n = int(round(duration_s * sr))
    samples: list[int] = []
    phase = 0.0
    for i in range(n):
        t = i / float(sr)
        freq = 1050.0 + 400.0 * math.sin(2.0 * math.pi * 0.45 * t)
        phase += 2.0 * math.pi * freq / float(sr)
        val = 0.6 * math.sin(phase) + 0.15 * math.sin(2.0 * phase)
        samples.append(max(-32767, min(32767, int(val * 32767.0))))
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sr,
        sr * 2,
        2,
        16,
        b"data",
        len(pcm),
    )
    return header + pcm


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    k = (len(ordered) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return ordered[int(k)]
    return ordered[f] * (c - k) + ordered[c] * (k - f)


def parse_mib(raw: str) -> float:
    token = raw.strip().split("/")[0].strip()
    if token.endswith("GiB"):
        return float(token[:-3]) * 1024.0
    if token.endswith("MiB"):
        return float(token[:-3])
    if token.endswith("KiB"):
        return float(token[:-3]) / 1024.0
    if token.endswith("GB"):
        return float(token[:-2]) * 953.674
    if token.endswith("MB"):
        return float(token[:-2]) * 0.953674
    if token.endswith("kB"):
        return float(token[:-2]) / 1048.576
    if token.endswith("B"):
        return float(token[:-1]) / (1024.0 * 1024.0)
    return 0.0


def sample_docker_memory(phase_label: str) -> list[dict[str, object]]:
    proc = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rows: list[dict[str, object]] = []
    for line in proc.stdout.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3 or "doppler" not in parts[0].lower():
            continue
        name, mem_usage, cpu_perc = parts
        rows.append(
            {
                "timestamp_utc": ts,
                "phase": phase_label,
                "service": name,
                "mem_mib": round(parse_mib(mem_usage), 2),
                "mem_raw": mem_usage.strip(),
                "cpu_percent": cpu_perc.strip(),
            }
        )
    return rows


def call_infer(wav_bytes: bytes) -> dict:
    req = urllib.request.Request(
        f"{INFERENCE_URL}/infer",
        data=wav_bytes,
        method="POST",
        headers={"Content-Type": "application/octet-stream"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_health() -> dict:
    with urllib.request.urlopen(f"{INFERENCE_URL}/health", timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark CPU reproducible Doppler")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--observations", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    n_obs = max(30, args.observations)
    n_warmup = max(3, args.warmup)

    health = get_health()
    assert health.get("ready") is True, f"Inference service not ready: {health}"

    mem_samples: list[dict[str, object]] = []
    # 5 muestras de memoria en reposo (1 Hz)
    for _ in range(5):
        mem_samples.extend(sample_docker_memory("reposo"))
        time.sleep(1.0)

    stop_mem = threading.Event()

    def mem_loop() -> None:
        while not stop_mem.is_set():
            mem_samples.extend(sample_docker_memory("carga_benchmark"))
            stop_mem.wait(1.0)

    mem_thread = threading.Thread(target=mem_loop, daemon=True)
    mem_thread.start()

    durations = [3.0, 6.0, 15.0, 30.0]
    observations: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    try:
        for dur in durations:
            wav_bytes = synth_wav_pcm16(dur, sr=16000)
            # Calentamiento separado (no incluido en percentiles)
            for _ in range(n_warmup):
                call_infer(wav_bytes)

            prep_list: list[float] = []
            inf_list: list[float] = []
            tot_list: list[float] = []
            win_count = 0

            for idx in range(1, n_obs + 1):
                res = call_infer(wav_bytes)
                timings = res["timings"]
                prep_ms = float(timings["decode_and_prepare_ms"])
                inf_ms = float(timings["inference_ms"])
                tot_ms = float(timings["total_ms"])
                win_count = int(res["windows_total"])

                prep_list.append(prep_ms)
                inf_list.append(inf_ms)
                tot_list.append(tot_ms)
                observations.append(
                    {
                        "duration_seconds": dur,
                        "windows_total": win_count,
                        "observation": idx,
                        "wav_bytes": len(wav_bytes),
                        "decode_and_prepare_ms": round(prep_ms, 3),
                        "inference_ms": round(inf_ms, 3),
                        "total_ms": round(tot_ms, 3),
                        "fixture_origin": "synthetic_pcm16_16khz_mono",
                    }
                )

            summary_rows.append(
                {
                    "duration_seconds": dur,
                    "windows_total": win_count,
                    "observations": n_obs,
                    "warmup_runs": n_warmup,
                    "prepare_p50_ms": round(percentile(prep_list, 50), 3),
                    "prepare_p95_ms": round(percentile(prep_list, 95), 3),
                    "inference_p50_ms": round(percentile(inf_list, 50), 3),
                    "inference_p95_ms": round(percentile(inf_list, 95), 3),
                    "total_p50_ms": round(percentile(tot_list, 50), 3),
                    "total_p95_ms": round(percentile(tot_list, 95), 3),
                    "total_mean_ms": round(statistics.mean(tot_list), 3),
                    "total_min_ms": round(min(tot_list), 3),
                    "total_max_ms": round(max(tot_list), 3),
                }
            )
    finally:
        stop_mem.set()
        mem_thread.join(timeout=3.0)

    # Guardar CSV de observaciones individuales
    obs_csv = out_dir / "benchmark_cpu_observaciones.csv"
    with obs_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(observations[0].keys()))
        writer.writeheader()
        writer.writerows(observations)

    # Guardar CSV + JSON de resumen CPU
    sum_csv = out_dir / "benchmark_cpu_resumen.csv"
    with sum_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    bench_summary = {
        "scope": "validacion_local_cpu",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "fixture_origin": "synthetic_pcm16_16khz_mono",
        "startup_model_load_ms": health.get("startup_load_ms"),
        "torch_version": health.get("torch_version"),
        "torch_num_threads": health.get("torch_num_threads"),
        "concurrency": 1,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "warmup_runs_per_condition": n_warmup,
        "observations_per_condition": n_obs,
        "conditions": summary_rows,
    }
    (out_dir / "benchmark_cpu_resumen.json").write_text(
        json.dumps(bench_summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Guardar memoria por servicio + resumen
    mem_csv = out_dir / "memoria_servicios.csv"
    if mem_samples:
        with mem_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(mem_samples[0].keys()))
            writer.writeheader()
            writer.writerows(mem_samples)

    by_service: dict[str, dict[str, list[float]]] = {}
    by_ts_total: dict[str, float] = {}
    for row in mem_samples:
        svc = str(row["service"])
        ph = str(row["phase"])
        mib = float(row["mem_mib"])
        ts = str(row["timestamp_utc"])
        by_service.setdefault(svc, {}).setdefault(ph, []).append(mib)
        by_ts_total[ts] = by_ts_total.get(ts, 0.0) + mib

    mem_summary: dict[str, object] = {
        "method": "docker stats --no-stream (RSS/working set reportado por cgroups)",
        "sampling_interval_seconds": 1.0,
        "total_samples": len(mem_samples),
        "services": {},
        "stack_total_mib": {
            "mean": round(statistics.mean(by_ts_total.values()), 2) if by_ts_total else 0.0,
            "max": round(max(by_ts_total.values()), 2) if by_ts_total else 0.0,
            "p95": round(percentile(list(by_ts_total.values()), 95), 2) if by_ts_total else 0.0,
        },
    }
    svc_map: dict[str, object] = mem_summary["services"]  # type: ignore[assignment]
    for svc, phases in sorted(by_service.items()):
        all_vals = [v for vals in phases.values() for v in vals]
        svc_map[svc] = {
            "reposo_mean_mib": round(statistics.mean(phases.get("reposo", [0.0])), 2),
            "carga_mean_mib": round(statistics.mean(phases.get("carga_benchmark", [0.0])), 2),
            "max_mib": round(max(all_vals), 2) if all_vals else 0.0,
            "p95_mib": round(percentile(all_vals, 95), 2) if all_vals else 0.0,
        }

    (out_dir / "memoria_servicios_resumen.json").write_text(
        json.dumps(mem_summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({"benchmark": bench_summary, "memory": mem_summary}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
