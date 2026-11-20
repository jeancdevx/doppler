from __future__ import annotations

import hashlib
import threading
import time

from doppler_inference.audio import prepare_wav_bytes
from doppler_inference.config import SAMPLE_RATE, WINDOW_SAMPLES, InferenceSettings
from doppler_inference.model import LoadedModelBundle
from doppler_inference.schemas import InferResponse, StageTimings, WindowPrediction


class InferenceEngine:
    """Coordina preparación e inferencia de forma serializada y segura en CPU."""

    def __init__(self, bundle: LoadedModelBundle, settings: InferenceSettings) -> None:
        self.bundle = bundle
        self.settings = settings
        self._lock = threading.Lock()

    def infer_wav_bytes(self, data: bytes) -> InferResponse:
        total_start = time.perf_counter()
        audio_sha256 = hashlib.sha256(data).hexdigest()

        prep_start = time.perf_counter()
        prepared = prepare_wav_bytes(data, max_duration_seconds=self.settings.max_duration_seconds)
        prep_ms = (time.perf_counter() - prep_start) * 1000.0

        if prepared.short_clip:
            total_ms = (time.perf_counter() - total_start) * 1000.0
            return InferResponse(
                audio_sha256=audio_sha256,
                model_sha256=self.bundle.model_sha256,
                contract_version=self.bundle.contract_version,
                contract_sha256=self.bundle.contract_sha256,
                threshold=self.bundle.threshold,
                score_type=self.bundle.score_type,
                audio=prepared.metadata,
                windows=[],
                windows_total=0,
                windows_positive=0,
                timings=StageTimings(
                    decode_and_prepare_ms=round(prep_ms, 3),
                    inference_ms=0.0,
                    total_ms=round(total_ms, 3),
                ),
                short_clip=True,
                short_clip_message=prepared.short_clip_message,
            )

        infer_start = time.perf_counter()
        with self._lock:
            scores = self.bundle.predict_scores(
                prepared.logmels,
                batch_size=self.settings.batch_size,
            )
        infer_ms = (time.perf_counter() - infer_start) * 1000.0

        windows: list[WindowPrediction] = []
        positive_count = 0
        for idx, (start_sample, raw_score) in enumerate(
            zip(prepared.window_starts, scores.tolist(), strict=True)
        ):
            score = float(raw_score)
            is_emergency = score >= self.bundle.threshold
            if is_emergency:
                positive_count += 1
            windows.append(
                WindowPrediction(
                    index=idx,
                    start_seconds=round(start_sample / float(SAMPLE_RATE), 4),
                    end_seconds=round((start_sample + WINDOW_SAMPLES) / float(SAMPLE_RATE), 4),
                    score=score,
                    label="EMERGENCY" if is_emergency else "NON_EMERGENCY",
                    margin_vs_threshold=score - self.bundle.threshold,
                )
            )

        total_ms = (time.perf_counter() - total_start) * 1000.0
        return InferResponse(
            audio_sha256=audio_sha256,
            model_sha256=self.bundle.model_sha256,
            contract_version=self.bundle.contract_version,
            contract_sha256=self.bundle.contract_sha256,
            threshold=self.bundle.threshold,
            score_type=self.bundle.score_type,
            audio=prepared.metadata,
            windows=windows,
            windows_total=len(windows),
            windows_positive=positive_count,
            timings=StageTimings(
                decode_and_prepare_ms=round(prep_ms, 3),
                inference_ms=round(infer_ms, 3),
                total_ms=round(total_ms, 3),
            ),
            short_clip=False,
            short_clip_message=None,
        )
