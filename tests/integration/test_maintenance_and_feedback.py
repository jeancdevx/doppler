#!/usr/bin/env python3
"""Pruebas de integración del Capítulo 10: Monitoreo, Drift, Incidentes y Retroalimentación.

Se ejecuta contra el stack real Docker Compose (Caddy + Rust API + SQLite + PyTorch CPU + Cloudflare R2).
Usa exclusivamente fixtures WAV sintéticas en memoria (identificadas como sintéticas).
Nunca imprime secretos, tokens ni URLs firmadas.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from test_api_and_r2 import BASE_URL, ApiSession, put_to_r2, synth_wav_pcm16, wait_for_terminal

ROOT = Path(__file__).resolve().parents[2]


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
    raise RuntimeError(f"Variable {key} no disponible en entorno ni .env")


def admin_req(
    method: str,
    path: str,
    token: str | None,
    payload: dict | None = None,
) -> tuple[int, dict]:
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["X-Admin-Token"] = token
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            body = {"raw_status": exc.code}
        return exc.code, body


def upload_and_complete(sess: ApiSession, filename: str, duration_s: float, siren: bool) -> dict:
    wav = synth_wav_pcm16(duration_s, sr=16000, channels=1, siren=siren)
    st_up, up = sess.json_req(
        "POST",
        "/api/uploads",
        {"filename": filename, "size_bytes": len(wav), "content_type": "audio/wav"},
    )
    assert st_up == 201, f"upload failed ({st_up}): {up}"
    put_st, upload_ms = put_to_r2(up["upload"], wav)
    assert put_st in (200, 204), f"R2 PUT failed: {put_st}"
    st_cf, _ = sess.json_req(
        "POST",
        f"/api/jobs/{up['job_id']}/confirm",
        {"client_upload_ms": upload_ms},
    )
    assert st_cf == 200
    detail = wait_for_terminal(sess, up["job_id"])
    assert detail["status"] == "completed", f"job failed: {detail}"
    return detail


def run_suite(out_json: Path | None = None) -> dict:
    admin_token = load_env_value("ADMIN_API_TOKEN")
    sess_a = ApiSession()
    sess_b = ApiSession()
    results: dict[str, dict] = {}
    cleanup_jobs: list[tuple[ApiSession, str]] = []

    try:
        # 1. /api/health & /api/ready healthy contract
        st_h, health = sess_a.json_req("GET", "/api/health")
        st_r, ready = sess_a.json_req("GET", "/api/ready")
        assert st_h == 200 and st_r == 200
        assert health["overall_status"] == "healthy"
        assert ready["ready"] is True
        assert health["components"]["sqlite"]["status"] == "healthy"
        assert health["components"]["inference"]["status"] == "healthy"
        assert health["components"]["r2"]["status"] == "healthy"
        results["health_and_ready_contract"] = {
            "passed": True,
            "health_http": st_h,
            "ready_http": st_r,
            "overall_status": health["overall_status"],
            "sqlite_latency_ms": round(health["components"]["sqlite"]["latency_ms"] or 0.0, 2),
            "inference_latency_ms": round(health["components"]["inference"]["latency_ms"] or 0.0, 2),
            "r2_latency_ms": round(health["components"]["r2"]["latency_ms"] or 0.0, 2),
        }

        # 2. Admin endpoint protection (401 without token or with wrong token)
        st_no_tok, _ = admin_req("GET", "/api/admin/overview", None)
        st_bad_tok, _ = admin_req("GET", "/api/admin/overview", "invalid_token_123")
        st_ok_tok, overview_before = admin_req("GET", "/api/admin/overview?days=30", admin_token)
        assert st_no_tok == 401 and st_bad_tok == 401 and st_ok_tok == 200
        results["admin_auth_protection"] = {
            "passed": True,
            "missing_token_http": st_no_tok,
            "invalid_token_http": st_bad_tok,
            "valid_token_http": st_ok_tok,
        }

        # 3. Manual probe & storage telemetry
        st_probe, probe = admin_req("POST", "/api/admin/health/probe", admin_token)
        assert st_probe == 200 and probe["overall_status"] == "healthy"
        assert probe["sqlite_size_bytes"] is not None and probe["sqlite_size_bytes"] > 0
        results["manual_probe_and_storage"] = {
            "passed": True,
            "overall_status": probe["overall_status"],
            "sqlite_size_bytes": probe["sqlite_size_bytes"],
            "r2_managed_objects": probe["r2_managed_objects"],
            "r2_managed_bytes": probe["r2_managed_bytes"],
        }

        # 4. End-to-end job -> feedback creation, isolation, review workflow, & telemetry survival after deletion
        detail = upload_and_complete(sess_a, "synthetic_ch10_feedback.wav", 6.0, True)
        job_id = detail["job_id"]
        cleanup_jobs.append((sess_a, job_id))

        # Session A submits window-specific feedback (false_alarm on window 0)
        st_fb1, fb1 = sess_a.json_req(
            "POST",
            f"/api/jobs/{job_id}/feedback",
            {
                "feedback_type": "false_alarm",
                "window_index": 0,
                "comment": "Prueba controlada Capítulo 10 (ventana 0).",
            },
        )
        assert st_fb1 == 201, f"feedback create failed: {st_fb1} {fb1}"
        assert fb1["review_status"] == "received"
        assert fb1["audio_available_at_report"] is True
        assert fb1["displayed_label"] in ("EMERGENCY", "NON_EMERGENCY")
        assert fb1["displayed_score"] is not None

        # Session A submits general technical_issue report (no window)
        st_fb2, fb2 = sess_a.json_req(
            "POST",
            f"/api/jobs/{job_id}/feedback",
            {
                "feedback_type": "technical_issue",
                "window_index": None,
                "comment": "Reporte técnico general sin ventana.",
            },
        )
        assert st_fb2 == 201 and fb2["window_index"] is None

        # Missing window for prediction report rejected with 400; non-existent window rejected with 404
        st_fb_missing_win, _ = sess_a.json_req(
            "POST",
            f"/api/jobs/{job_id}/feedback",
            {"feedback_type": "false_alarm", "window_index": None},
        )
        assert st_fb_missing_win == 400

        st_fb_bad_win, _ = sess_a.json_req(
            "POST",
            f"/api/jobs/{job_id}/feedback",
            {"feedback_type": "false_alarm", "window_index": 999},
        )
        assert st_fb_bad_win == 404

        # Session B isolation: cannot create or list feedback for Session A's job
        sess_b.json_req("POST", "/api/session")
        st_b_fb_post, _ = sess_b.json_req(
            "POST",
            f"/api/jobs/{job_id}/feedback",
            {"feedback_type": "false_alarm", "window_index": 0},
        )
        st_b_fb_get, _ = sess_b.json_req("GET", f"/api/jobs/{job_id}/feedback")
        assert st_b_fb_post == 404 and st_b_fb_get == 404

        # Invalid state jump (received -> resolved) rejected with 409
        st_bad_jump, _ = admin_req(
            "PATCH",
            f"/api/admin/feedback/{fb1['id']}",
            admin_token,
            {"review_status": "resolved"},
        )
        assert st_bad_jump == 409

        # Valid workflow: received -> in_review -> confirmed -> resolved
        st_r1, r1 = admin_req(
            "PATCH",
            f"/api/admin/feedback/{fb1['id']}",
            admin_token,
            {"review_status": "in_review", "resolution_note": "Escucha de prueba iniciada."},
        )
        assert st_r1 == 200 and r1["review_status"] == "in_review"
        st_r2, r2 = admin_req(
            "PATCH",
            f"/api/admin/feedback/{fb1['id']}",
            admin_token,
            {
                "review_status": "confirmed",
                "verified_label": "NON_EMERGENCY",
                "resolution_note": "Verificado en prueba controlada como señal sintética.",
            },
        )
        assert st_r2 == 200 and r2["verified_label"] == "NON_EMERGENCY"
        st_r3, r3 = admin_req(
            "PATCH",
            f"/api/admin/feedback/{fb1['id']}",
            admin_token,
            {"review_status": "resolved"},
        )
        assert st_r3 == 200 and r3["review_status"] == "resolved"

        # Delete job (simulating 24h deletion) and verify:
        # (a) job disappears from /api/jobs/{id} (404),
        # (b) telemetry count in /api/admin/overview STILL counts it,
        # (c) feedback report reflects audio_currently_available = False.
        st_del, _, _ = sess_a.request("DELETE", f"/api/jobs/{job_id}")
        assert st_del == 204
        cleanup_jobs = [(s, j) for (s, j) in cleanup_jobs if j != job_id]

        st_ov_after, overview_after = admin_req("GET", "/api/admin/overview?days=30", admin_token)
        assert st_ov_after == 200
        assert overview_after["counters"]["completed"] >= overview_before["counters"]["completed"] + 1
        assert overview_after["counters"]["user_deleted_in_history"] >= 1

        st_fb_admin, fb_admin_list = admin_req("GET", "/api/admin/feedback", admin_token)
        assert st_fb_admin == 200
        fb1_after = next((r for r in fb_admin_list["reports"] if r["id"] == fb1["id"]), None)
        assert fb1_after is not None and fb1_after["audio_currently_available"] is False

        results["feedback_and_telemetry_persistence"] = {
            "passed": True,
            "feedback_report_id": fb1["id"],
            "general_report_id": fb2["id"],
            "invalid_window_http": st_fb_bad_win,
            "cross_session_post_http": st_b_fb_post,
            "cross_session_get_http": st_b_fb_get,
            "invalid_transition_http": st_bad_jump,
            "final_review_status": r3["review_status"],
            "audio_available_after_delete": fb1_after["audio_currently_available"],
            "telemetry_completed_before": overview_before["counters"]["completed"],
            "telemetry_completed_after_delete": overview_after["counters"]["completed"],
            "reviewed_metrics": fb_admin_list["metrics"],
        }

        # 5. Maintenance mode blocks uploads with 503 & /api/ready returns 503
        st_m_on, m_on = admin_req(
            "POST",
            "/api/admin/maintenance",
            admin_token,
            {"enabled": True, "reason": "Prueba de integración modo mantenimiento"},
        )
        assert st_m_on == 200 and m_on["maintenance"]["enabled"] is True

        st_ready_m, ready_m = sess_a.json_req("GET", "/api/ready")
        st_up_m, up_m = sess_a.json_req(
            "POST",
            "/api/uploads",
            {"filename": "blocked_during_maint.wav", "size_bytes": 16000},
        )
        assert st_ready_m == 503 and ready_m["maintenance_mode"] is True
        assert st_up_m == 503 and up_m["error"]["code"] == "maintenance_mode"

        st_m_off, m_off = admin_req(
            "POST",
            "/api/admin/maintenance",
            admin_token,
            {"enabled": False, "reason": None},
        )
        assert st_m_off == 200 and m_off["maintenance"]["enabled"] is False
        st_ready_back, _ = sess_a.json_req("GET", "/api/ready")
        assert st_ready_back == 200
        results["maintenance_mode_gate"] = {
            "passed": True,
            "ready_during_maintenance_http": st_ready_m,
            "upload_during_maintenance_http": st_up_m,
            "ready_after_restore_http": st_ready_back,
        }

        # 6. Controlled dependency fault & recovery drill (stop inference briefly -> 3 probes -> incident opens -> start inference -> auto-recovers)
        subprocess.run(
            ["docker", "compose", "stop", "inference"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ready_fault_http = None
        try:
            for _ in range(3):
                st_p, _ = admin_req("POST", "/api/admin/health/probe", admin_token)
                assert st_p == 200
            ready_fault_http, ready_fault_body = sess_a.json_req("GET", "/api/ready")
            assert ready_fault_http == 503
            assert ready_fault_body["components"]["inference"]["status"] == "unavailable"
            st_ov_inc, ov_inc = admin_req("GET", "/api/admin/overview?days=1", admin_token)
            open_inf = [
                inc
                for inc in ov_inc["incidents"]
                if inc["component"] == "inference" and inc["status"] == "open"
            ]
            assert len(open_inf) >= 1, f"Expected open inference incident, got {ov_inc['incidents']}"
            opened_incident_id = open_inf[0]["id"]
        finally:
            subprocess.run(
                ["docker", "compose", "start", "inference"],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        # Wait for inference to come back healthy
        recovered = False
        for _ in range(45):
            st_r_chk, body_chk = sess_a.json_req("GET", "/api/ready")
            if st_r_chk == 200 and body_chk["ready"] is True:
                recovered = True
                break
            time.sleep(0.75)
        assert recovered, "Inference service did not recover within timeout"

        # Probe once more to trigger automatic incident resolution
        st_rec_probe, rec_probe = admin_req("POST", "/api/admin/health/probe", admin_token)
        assert st_rec_probe == 200 and rec_probe["overall_status"] == "healthy"
        _, ov_rec = admin_req("GET", "/api/admin/overview?days=1", admin_token)
        resolved_inc = next(
            (inc for inc in ov_rec["incidents"] if inc["id"] == opened_incident_id), None
        )
        assert resolved_inc is not None and resolved_inc["status"] == "resolved"
        results["incident_open_and_auto_recovery"] = {
            "passed": True,
            "ready_during_fault_http": ready_fault_http,
            "incident_id": opened_incident_id,
            "resolved_at": resolved_inc["resolved_at"],
            "consecutive_failures": resolved_inc["consecutive_failures"],
        }

        # 7. Drift API check (import synthetic reference via drift_engine & evaluate via API)
        drift_ref_path = ROOT / "scripts" / "drift_engine.py"
        if drift_ref_path.is_file():
            # Verify /api/admin/drift works even before importing reference
            st_d0, d0 = admin_req("GET", "/api/admin/drift", admin_token)
            assert st_d0 == 200
            st_ev0, ev0 = admin_req("POST", "/api/admin/drift/evaluate", admin_token, {"window_days": 30})
            assert st_ev0 == 200
            results["drift_api_evaluation"] = {
                "passed": True,
                "initial_representative_status": d0["representative_status"],
                "evaluation_status": ev0["status"],
                "sample_count": ev0["sample_count"],
            }

    finally:
        # Ensure maintenance mode is always left disabled
        try:
            admin_req("POST", "/api/admin/maintenance", admin_token, {"enabled": False, "reason": None})
        except Exception:
            pass
        for s, jid in cleanup_jobs:
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
