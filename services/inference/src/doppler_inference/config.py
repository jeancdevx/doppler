from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CONTRACT_VERSION = "doppler-resnet18-v3-contract-1.0.0"

SAMPLE_RATE = 16000
WINDOW_SECONDS = 3.0
HOP_SECONDS = 1.5
WINDOW_SAMPLES = int(round(WINDOW_SECONDS * SAMPLE_RATE))  # 48000
HOP_SAMPLES = int(round(HOP_SECONDS * SAMPLE_RATE))  # 24000
PEAK_TARGET = 0.99
SILENCE_PEAK = 1e-6
N_FFT = 2048
STFT_HOP = 512
N_MELS = 64
FMIN = 20.0
FMAX = 8000.0
DB_AMIN = 1e-10
TOP_DB = 80.0
EXPECTED_LOGMEL_SHAPE = (N_MELS, 1 + WINDOW_SAMPLES // STFT_HOP)  # (64, 94)


@dataclass(frozen=True)
class InferenceSettings:
    model_path: Path
    inference_config_path: Path
    max_file_bytes: int
    max_duration_seconds: float
    torch_num_threads: int
    batch_size: int

    @classmethod
    def from_env(cls) -> InferenceSettings:
        model_path = Path(os.environ.get("CONTAINER_MODEL_PATH", "/models/model.pt"))
        config_path = Path(
            os.environ.get("CONTAINER_INFERENCE_CONFIG_PATH", "/models/inference.json")
        )
        return cls(
            model_path=model_path,
            inference_config_path=config_path,
            max_file_bytes=int(os.environ.get("MAX_FILE_BYTES", "26214400")),
            max_duration_seconds=float(os.environ.get("MAX_DURATION_SECONDS", "120")),
            torch_num_threads=max(1, int(os.environ.get("TORCH_NUM_THREADS", "4"))),
            batch_size=max(1, int(os.environ.get("INFERENCE_BATCH_SIZE", "32"))),
        )
