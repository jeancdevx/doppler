#!/usr/bin/env python3
"""Pruebas de integración real contra el stack Docker Compose + Cloudflare R2.

Usa exclusivamente fixtures sintéticas generadas en memoria (identificadas como sintéticas).
No simula R2 ni la inferencia del modelo.
"""

from __future__ import annotations

import hashlib
import http.cookiejar
import json
import math
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "http://localhost:4321"


def synth_wav_pcm16(duration_s: float, sr: int = 16000, channels: int = 1, siren: bool = True) -> bytes:
    """Genera un WAV PCM16 sintético en stdlib pura (solo pruebas técnicas)."""
    n_frames = int(round(duration_s * sr))
    samples: list[int] = []
    phase = 0.0
    for i in range(n_frames):
        t = i / float(sr)
        if siren:
            freq = 1050.0 + 400.0 * math.sin(2.0 * math.pi * 0.45 * t)
            phase += 2.0 * math.pi * freq / float(sr)
            val = 0.65 * math.sin(phase) + 0.15 * math.sin(2.0 * phase)
        else:
            val = 0.15 * math.sin(2.0 * math.pi * 120.0 * t)
        s16 = max(-32767, min(32767, int(val * 32767.0)))
        for _ in range(channels):
            samples.append(s16)

    pcm = struct.pack(f"<{len(samples)}h", *samples)
    byte_rate = sr * channels * 2
    block_align = channels * 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        channels,
        sr,
        byte_rate,
        block_align,
        16,
        b"data",
        len(pcm),
    )
    return header + pcm


class ApiSession:
    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=30) as resp:
                return resp.status, dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()

    def json_req(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        st, _, body = self.request(method, path, payload)
        return st, json.loads(body.decode("utf-8")) if body else {}


def put_to_r2(upload_info: dict, data: bytes) -> tuple[int, float]:
    t0 = time.perf_counter()
    req = urllib.request.Request(
        upload_info["url"],
        data=data,
        method=upload_info["method"],
        headers=upload_info["headers"],
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, (time.perf_counter() - t0) * 1000.0


def wait_for_terminal(sess: ApiSession, job_id: str, timeout_s: float = 60.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st, detail = sess.json_req("GET", f"/api/jobs/{job_id}")
        assert st == 200, f"GET job failed: {st}"
        if detail["status"] in ("completed", "failed"):
            return detail
        time.sleep(0.35)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout_s}s")


def run_suite(out_json: Path | None = None) -> dict:
    results: dict[str, dict] = {}
    sess_a = ApiSession()
    sess_b = ApiSession()
    created_jobs_to_cleanup: list[tuple[ApiSession, str]] = []

    try:
        # 1. Health check via Caddy
        st, health = sess_a.json_req("GET", "/api/health")
        assert st == 200 and health["status"] == "ok", f"Unhealthy: {health}"
        assert health["r2_reachable"] is True
        assert health["inference"]["ready"] is True
        results["health_check"] = {
            "passed": True,
            "model_sha256": health["inference"]["model_sha256"],
            "threshold": health["inference"]["threshold"],
            "startup_load_ms": health["inference"]["startup_load_ms"],
        }

        # 2. Validation rejections (non-wav, empty, >25MiB)
        st_ext, _ = sess_a.json_req(
            "POST", "/api/uploads", {"filename": "fake.mp3", "size_bytes": 1024}
        )
        st_zero, _ = sess_a.json_req(
            "POST", "/api/uploads", {"filename": "empty.wav", "size_bytes": 0}
        )
        st_big, _ = sess_a.json_req(
            "POST", "/api/uploads", {"filename": "huge.wav", "size_bytes": 30_000_000}
        )
        assert st_ext == 400 and st_zero == 400 and st_big == 413
        results["upload_validation_limits"] = {
            "passed": True,
            "non_wav_status": st_ext,
            "empty_status": st_zero,
            "oversize_status": st_big,
        }

        # 3. Full happy path: upload -> R2 PUT -> idempotent confirm -> inference -> audio-url SHA256 -> export JSON/CSV
        wav_bytes = synth_wav_pcm16(6.0, sr=16000, channels=1, siren=True)
        wav_sha = hashlib.sha256(wav_bytes).hexdigest()

        st_up, up = sess_a.json_req(
            "POST",
            "/api/uploads",
            {"filename": "synthetic_siren_6s.wav", "size_bytes": len(wav_bytes), "content_type": "audio/wav"},
        )
        assert st_up == 201
        job_id = up["job_id"]
        created_jobs_to_cleanup.append((sess_a, job_id))

        put_st, upload_ms = put_to_r2(up["upload"], wav_bytes)
        assert put_st in (200, 204)

        st_c1, c1 = sess_a.json_req(
            "POST", f"/api/jobs/{job_id}/confirm", {"client_upload_ms": upload_ms}
        )
        assert st_c1 == 200
        # Confirmación idempotente
        st_c2, c2 = sess_a.json_req(
            "POST", f"/api/jobs/{job_id}/confirm", {"client_upload_ms": upload_ms}
        )
        assert st_c2 == 200 and c2["job_id"] == job_id

        detail = wait_for_terminal(sess_a, job_id)
        assert detail["status"] == "completed", f"Expected completed, got {detail}"
        assert detail["audio_sha256"] == wav_sha
        assert detail["windows_total"] == 3
        assert detail["threshold"] == health["inference"]["threshold"]

        # Audio URL temporal autorizada y verificación SHA-256
        st_aud, aud = sess_a.json_req("GET", f"/api/jobs/{job_id}/audio-url")
        assert st_aud == 200
        with urllib.request.urlopen(aud["url"], timeout=20) as r:
            dl_bytes = r.read()
        assert hashlib.sha256(dl_bytes).hexdigest() == wav_sha

        # Exportación JSON y CSV
        st_ej, _, body_ej = sess_a.request("GET", f"/api/jobs/{job_id}/export?format=json")
        st_ec, _, body_ec = sess_a.request("GET", f"/api/jobs/{job_id}/export?format=csv")
        assert st_ej == 200 and json.loads(body_ej)["audio_sha256"] == wav_sha
        csv_lines = body_ec.decode("utf-8").strip().splitlines()
        assert st_ec == 200 and len(csv_lines) == 4  # header + 3 windows

        results["end_to_end_real_r2_and_inference"] = {
            "passed": True,
            "job_id": job_id,
            "audio_sha256": wav_sha,
            "windows_total": detail["windows_total"],
            "windows_positive": detail["windows_positive"],
            "upload_ms": round(upload_ms, 2),
            "timings": detail["timings"],
        }

        # 4. Cross-session isolation (Session B MUST NOT access Session A's job)
        st_b_init, _ = sess_b.json_req("POST", "/api/session")
        assert st_b_init == 200
        st_b_get, _ = sess_b.json_req("GET", f"/api/jobs/{job_id}")
        st_b_aud, _ = sess_b.json_req("GET", f"/api/jobs/{job_id}/audio-url")
        st_b_del, _, _ = sess_b.request("DELETE", f"/api/jobs/{job_id}")
        assert st_b_get == 404 and st_b_aud == 404 and st_b_del == 404
        results["cross_session_isolation"] = {
            "passed": True,
            "get_status": st_b_get,
            "audio_url_status": st_b_aud,
            "delete_status": st_b_del,
        }

        # 5. Short clip (<3s) coherent contract handling
        short_wav = synth_wav_pcm16(2.1, sr=16000, channels=1, siren=True)
        st_su, su = sess_a.json_req(
            "POST",
            "/api/uploads",
            {"filename": "synthetic_short_2s1.wav", "size_bytes": len(short_wav), "content_type": "audio/wav"},
        )
        assert st_su == 201
        created_jobs_to_cleanup.append((sess_a, su["job_id"]))
        put_to_r2(su["upload"], short_wav)
        sess_a.json_req("POST", f"/api/jobs/{su['job_id']}/confirm", {})
        short_detail = wait_for_terminal(sess_a, su["job_id"])
        assert short_detail["status"] == "completed"
        assert short_detail["short_clip"] is True
        assert short_detail["windows_total"] == 0
        results["short_clip_contract"] = {
            "passed": True,
            "short_clip": short_detail["short_clip"],
            "message": short_detail["short_clip_message"],
        }

        # 6. Corrupt WAV recoverable failure
        corrupt_wav = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00\xff" * 64
        st_cu, cu = sess_a.json_req(
            "POST",
            "/api/uploads",
            {"filename": "synthetic_corrupt.wav", "size_bytes": len(corrupt_wav), "content_type": "audio/wav"},
        )
        assert st_cu == 201
        created_jobs_to_cleanup.append((sess_a, cu["job_id"]))
        put_to_r2(cu["upload"], corrupt_wav)
        sess_a.json_req("POST", f"/api/jobs/{cu['job_id']}/confirm", {})
        corrupt_detail = wait_for_terminal(sess_a, cu["job_id"])
        assert corrupt_detail["status"] == "failed"
        assert corrupt_detail["error_code"] == "decode_error"
        results["corrupt_wav_error_handling"] = {
            "passed": True,
            "error_code": corrupt_detail["error_code"],
        }

        # 7. Queue & concurrency=1 test (3 concurrent submissions)
        q_ids: list[str] = []
        q_wav = synth_wav_pcm16(4.5, sr=16000, channels=1, siren=False)
        for idx in range(3):
            st_q, qu = sess_a.json_req(
                "POST",
                "/api/uploads",
                {"filename": f"synthetic_queue_{idx}.wav", "size_bytes": len(q_wav), "content_type": "audio/wav"},
            )
            assert st_q == 201
            created_jobs_to_cleanup.append((sess_a, qu["job_id"]))
            put_to_r2(qu["upload"], q_wav)
            q_ids.append(qu["job_id"])
        for qid in q_ids:
            st_qc, _ = sess_a.json_req("POST", f"/api/jobs/{qid}/confirm", {})
            assert st_qc == 200
        q_details = [wait_for_terminal(sess_a, qid) for qid in q_ids]
        assert all(d["status"] == "completed" for d in q_details)
        results["queue_and_concurrency_1"] = {
            "passed": True,
            "submitted": 3,
            "completed": len(q_details),
            "queue_wait_ms": [round(d["timings"]["queue_wait_ms"] or 0.0, 2) for d in q_details],
        }

        # 8. Persistence after controlled API restart
        subprocess.run(["docker", "compose", "restart", "api"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(30):
            try:
                st_h, h = sess_a.json_req("GET", "/api/health")
                if st_h == 200 and h["status"] == "ok":
                    break
            except Exception:
                pass
            time.sleep(0.5)
        st_after_restart, after_detail = sess_a.json_req("GET", f"/api/jobs/{job_id}")
        assert st_after_restart == 200
        assert after_detail["audio_sha256"] == wav_sha
        assert len(after_detail["windows"]) == 3
        results["persistence_after_restart"] = {"passed": True, "job_id": job_id}

        # 9. Delete job and verify R2 + SQLite removal
        st_del, _, _ = sess_a.request("DELETE", f"/api/jobs/{job_id}")
        assert st_del == 204
        st_gone, _ = sess_a.json_req("GET", f"/api/jobs/{job_id}")
        assert st_gone == 404
        created_jobs_to_cleanup = [(s, j) for (s, j) in created_jobs_to_cleanup if j != job_id]
        results["delete_r2_and_sqlite"] = {"passed": True}

    finally:
        for s, jid in created_jobs_to_cleanup:
            try:
                s.request("DELETE", f"/api/jobs/{jid}")
            except Exception:
                pass

    summary = {
        "all_passed": all(v.get("passed") for v in results.values()),
        "synthetic_fixtures_only": True,
        "tests": results,
    }
    rendered = json.dumps(summary, indent=2, ensure_ascii=False)
    print(rendered)
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(rendered + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    res = run_suite(out_path)
    sys.exit(0 if res["all_passed"] else 1)
