"""Pruebas de paridad independiente y matriz de archivos WAV (fixtures sintéticas)."""

from __future__ import annotations

import io
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from notebook_reference import nb_load_and_score

from doppler_inference.audio import prepare_wav_bytes
from doppler_inference.main import app

MODEL_PATH = Path(os.environ.get("CONTAINER_MODEL_PATH", "/models/model.pt"))


def synth_siren_signal(duration_s: float, sr: int, channels: int = 1) -> np.ndarray:
    """Genera una señal sintética modulada tipo barrido sinusoidal (solo pruebas técnicas)."""
    n = int(round(duration_s * sr))
    t = np.arange(n, dtype=np.float64) / float(sr)
    # Barrido tipo wail 650-1500 Hz + ruido ambiental leve
    freq = 1075.0 + 425.0 * np.sin(2.0 * np.pi * 0.45 * t)
    phase = 2.0 * np.pi * np.cumsum(freq) / float(sr)
    rng = np.random.default_rng(42)
    sig = 0.55 * np.sin(phase) + 0.15 * np.sin(2.0 * phase) + 0.04 * rng.standard_normal(n)
    sig = np.clip(sig, -0.95, 0.95).astype(np.float32)
    if channels == 1:
        return sig[:, None]
    # Estéreo con ligera variación de fase/nivel
    ch2 = np.roll(sig, 5) * 0.85
    return np.stack([sig, ch2], axis=1).astype(np.float32)


def synth_traffic_noise(duration_s: float, sr: int) -> np.ndarray:
    """Genera ruido sintético de baja frecuencia (solo pruebas técnicas)."""
    n = int(round(duration_s * sr))
    rng = np.random.default_rng(123)
    white = rng.standard_normal(n)
    # Filtro paso bajo simple por promedio móvil
    kernel = np.ones(25) / 25.0
    low = np.convolve(white, kernel, mode="same")
    low = (low / (np.max(np.abs(low)) + 1e-8) * 0.4).astype(np.float32)
    return low[:, None]


def encode_wav(samples: np.ndarray, sr: int, subtype: str = "PCM_16") -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV", subtype=subtype)
    return buf.getvalue()


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_health_and_ready(client: TestClient) -> None:
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["model_loaded"] is True
    assert body["threshold"] == pytest.approx(0.6547843813896179, abs=1e-12)
    assert body["input_shape"] == [64, 94]
    expected_hash = (
        "e0dc2eaa1415f66d7442a8db7cf249129520ece20d575df35dc0aefb29f89d2a"
    )
    assert body["model_sha256"] == expected_hash


@pytest.mark.parametrize(
    ("name", "duration_s", "sr", "channels", "kind"),
    [
        ("siren_mono_16k_6s", 6.0, 16000, 1, "siren"),
        ("siren_stereo_44k1_7s2", 7.2, 44100, 2, "siren"),
        ("noise_mono_48k_5s", 5.0, 48000, 1, "noise"),
        ("siren_mono_8k_4s5", 4.5, 8000, 1, "siren"),
        ("noise_stereo_22k05_3s", 3.0, 22050, 2, "noise"),
        ("silence_mono_16k_4s5", 4.5, 16000, 1, "silence"),
    ],
)
def test_independent_notebook_parity(
    client: TestClient,
    tmp_path: Path,
    name: str,
    duration_s: float,
    sr: int,
    channels: int,
    kind: str,
) -> None:
    if kind == "siren":
        samples = synth_siren_signal(duration_s, sr, channels=channels)
    elif kind == "noise":
        samples = synth_traffic_noise(duration_s, sr)
        if channels == 2:
            samples = np.concatenate([samples, samples * 0.9], axis=1)
    else:
        samples = np.zeros((int(round(duration_s * sr)), channels), dtype=np.float32)

    wav_bytes = encode_wav(samples, sr)
    wav_file = tmp_path / f"{name}.wav"
    wav_file.write_bytes(wav_bytes)

    ref = nb_load_and_score(MODEL_PATH, wav_file)

    prepared = prepare_wav_bytes(wav_bytes, max_duration_seconds=120.0)
    assert prepared.window_starts == ref["starts"]
    for idx, ref_lm in enumerate(ref["logmels"]):
        max_lm_diff = float(np.max(np.abs(prepared.logmels[idx] - ref_lm)))
        assert max_lm_diff <= 1e-5, f"{name} window {idx}: logmel diff {max_lm_diff}"

    resp = client.post(
        "/infer",
        content=wav_bytes,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["short_clip"] is False
    assert body["windows_total"] == len(ref["scores"])

    for win, ref_score, ref_label in zip(
        body["windows"], ref["scores"], ref["labels"], strict=True
    ):
        assert abs(win["score"] - ref_score) <= 1e-5
        assert win["label"] == ref_label


def test_short_clip_under_3_seconds_not_padded(client: TestClient) -> None:
    samples = synth_siren_signal(2.4, 16000, channels=1)
    wav_bytes = encode_wav(samples, 16000)
    resp = client.post(
        "/infer",
        content=wav_bytes,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["short_clip"] is True
    assert body["windows_total"] == 0
    assert body["windows"] == []
    assert "3.0 s" in (body["short_clip_message"] or "")


def test_boundary_durations_and_incomplete_tail(client: TestClient) -> None:
    # Exact 3.0s -> 1 window, 0 tail
    r3 = client.post("/infer", content=encode_wav(synth_siren_signal(3.0, 16000), 16000)).json()
    assert r3["windows_total"] == 1
    assert r3["audio"]["discarded_tail_samples"] == 0

    # 4.49s -> still only 1 complete window, tail ~1.49s discarded
    r449 = client.post("/infer", content=encode_wav(synth_siren_signal(4.49, 16000), 16000)).json()
    assert r449["windows_total"] == 1
    assert r449["audio"]["discarded_tail_seconds"] == pytest.approx(1.49, abs=0.02)

    # Exact 4.5s -> 2 complete windows, 0 tail
    r45 = client.post("/infer", content=encode_wav(synth_siren_signal(4.5, 16000), 16000)).json()
    assert r45["windows_total"] == 2
    assert r45["audio"]["discarded_tail_samples"] == 0

    # 5.2s -> 2 complete windows, 0.7s tail discarded
    r52 = client.post("/infer", content=encode_wav(synth_siren_signal(5.2, 16000), 16000)).json()
    assert r52["windows_total"] == 2
    assert r52["audio"]["discarded_tail_seconds"] == pytest.approx(0.7, abs=0.01)


def test_invalid_empty_corrupt_fake_and_excess_duration(client: TestClient) -> None:
    # Empty
    r_empty = client.post("/infer", content=b"")
    assert r_empty.status_code == 422

    # Fake WAV (plain text / fake extension)
    r_fake = client.post("/infer", content=b"ID3\x03\x00This is not a real wav file" * 4)
    assert r_fake.status_code == 422
    assert r_fake.json()["detail"]["code"] == "invalid_format"

    # Corrupt RIFF/WAVE header with garbage payload
    r_corrupt = client.post("/infer", content=b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\xff" * 64)
    assert r_corrupt.status_code == 422
    assert r_corrupt.json()["detail"]["code"] == "decode_error"

    # Duration > 120s (121s at 8kHz mono PCM_16 = ~1.9 MB, well under 25 MiB)
    long_samples = np.zeros((121 * 8000, 1), dtype=np.float32)
    r_long = client.post("/infer", content=encode_wav(long_samples, 8000))
    assert r_long.status_code == 422
    assert r_long.json()["detail"]["code"] == "duration_exceeded"
