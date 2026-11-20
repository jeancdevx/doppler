from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torchvision.models import resnet18

from doppler_inference.config import (
    CONTRACT_VERSION,
    DB_AMIN,
    EXPECTED_LOGMEL_SHAPE,
    FMAX,
    FMIN,
    HOP_SECONDS,
    N_FFT,
    N_MELS,
    PEAK_TARGET,
    SAMPLE_RATE,
    STFT_HOP,
    TOP_DB,
    WINDOW_SECONDS,
)


class ModelLoadError(RuntimeError):
    """Error de configuración o integridad del checkpoint del modelo."""


class VisualTransfer(nn.Module):
    """Arquitectura exacta extraída de 05_resnet18.ipynb (celda 71)."""

    def __init__(self, dropout: float) -> None:
        super().__init__()
        self.net = resnet18(weights=None)
        self.net.fc = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(self.net.fc.in_features, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x.repeat(1, 3, 1, 1)).squeeze(1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class LoadedModelBundle:
    model: VisualTransfer
    mean: np.ndarray
    std: np.ndarray
    threshold: float
    score_type: str
    input_shape: tuple[int, int]
    model_sha256: str
    contract_version: str
    contract_sha256: str
    startup_load_ms: float
    dropout: float

    def predict_scores(self, logmels: np.ndarray, batch_size: int = 32) -> np.ndarray:
        """Ejecuta inferencia CPU determinista sin AMP sobre lote (W, 64, 94) float32."""
        if len(logmels) == 0:
            return np.empty((0,), dtype=np.float32)

        standardized = (logmels - self.mean[None, :, None]) / self.std[None, :, None]
        standardized = np.ascontiguousarray(standardized[:, None, :, :], dtype=np.float32)

        scores: list[np.ndarray] = []
        with torch.inference_mode():
            for start in range(0, len(standardized), batch_size):
                batch_tensor = torch.from_numpy(standardized[start : start + batch_size])
                logits = self.model(batch_tensor)
                probs = torch.sigmoid(logits.float()).cpu().numpy()
                scores.append(probs)
        return np.concatenate(scores, axis=0)


def load_model_bundle(
    model_path: Path,
    inference_config_path: Path,
    torch_num_threads: int,
) -> LoadedModelBundle:
    """Carga el checkpoint entrenado en CPU sin descargar pesos ImageNet."""
    started = time.perf_counter()

    if not model_path.is_file():
        raise ModelLoadError(f"No existe el archivo de checkpoint del modelo: {model_path}")
    if not inference_config_path.is_file():
        raise ModelLoadError(f"No existe inference.json en: {inference_config_path}")

    torch.set_num_threads(torch_num_threads)

    model_hash = sha256_file(model_path)
    inference_cfg = json.loads(inference_config_path.read_text(encoding="utf-8"))

    artifact = torch.load(model_path, map_location="cpu", weights_only=True)
    if not isinstance(artifact, dict) or "state_dict" not in artifact:
        raise ModelLoadError(
            "El archivo .pt no contiene el diccionario exportado por Doppler (falta state_dict). "
            "No se admiten pesos ImageNet sin entrenar."
        )

    if artifact.get("model_kind") != "resnet":
        raise ModelLoadError(
            f"Arquitectura incompatible en checkpoint: {artifact.get('model_kind')!r}."
        )

    class_map = artifact.get("class_map")
    if class_map != {"0": "NON_EMERGENCY", "1": "EMERGENCY"}:
        raise ModelLoadError(f"Mapeo de clases inesperado: {class_map!r}.")

    input_shape = tuple(int(v) for v in artifact.get("input_shape", []))
    if input_shape != EXPECTED_LOGMEL_SHAPE:
        raise ModelLoadError(
            f"Forma de entrada incompatible: {input_shape}, esperada {EXPECTED_LOGMEL_SHAPE}."
        )

    params = artifact.get("params") or {}
    if "dropout" not in params:
        raise ModelLoadError("El checkpoint no declara params.dropout.")
    dropout = float(params["dropout"])

    threshold = float(artifact["threshold"])
    cfg_threshold = float(inference_cfg["threshold"])
    if abs(threshold - cfg_threshold) > 1e-12:
        raise ModelLoadError(
            f"Desalineación de umbral entre model.pt ({threshold}) "
            f"e inference.json ({cfg_threshold})."
        )

    mean = np.asarray(artifact["normalization_mean"], dtype=np.float32)
    std = np.asarray(artifact["normalization_std"], dtype=np.float32)
    cfg_mean = np.asarray(inference_cfg["normalization_mean"], dtype=np.float32)
    cfg_std = np.asarray(inference_cfg["normalization_std"], dtype=np.float32)

    if mean.shape != (N_MELS,) or std.shape != (N_MELS,):
        raise ModelLoadError(f"Dimensiones de normalización inválidas: {mean.shape}, {std.shape}.")
    if not np.allclose(mean, cfg_mean, atol=1e-6) or not np.allclose(std, cfg_std, atol=1e-6):
        raise ModelLoadError(
            "Desalineación de estadísticas de normalización entre model.pt e inference.json."
        )
    if not np.isfinite(mean).all() or not np.isfinite(std).all() or (std <= 0).any():
        raise ModelLoadError("Estadísticas de normalización no finitas o con std <= 0.")

    model = VisualTransfer(dropout=dropout)
    model.load_state_dict(artifact["state_dict"], strict=True)
    model.eval()

    score_type = str(artifact.get("score_type", "sigmoid_probability_not_calibrated"))
    contract_payload = {
        "contract_version": CONTRACT_VERSION,
        "model_kind": "resnet",
        "dropout": dropout,
        "sample_rate": SAMPLE_RATE,
        "window_seconds": WINDOW_SECONDS,
        "hop_seconds": HOP_SECONDS,
        "peak_target": PEAK_TARGET,
        "n_fft": N_FFT,
        "stft_hop": STFT_HOP,
        "n_mels": N_MELS,
        "fmin": FMIN,
        "fmax": FMAX,
        "db_amin": DB_AMIN,
        "top_db": TOP_DB,
        "input_shape": list(EXPECTED_LOGMEL_SHAPE),
        "threshold": threshold,
        "score_type": score_type,
        "normalization_mean": [float(v) for v in mean],
        "normalization_std": [float(v) for v in std],
    }
    contract_sha256 = hashlib.sha256(
        json.dumps(contract_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return LoadedModelBundle(
        model=model,
        mean=mean,
        std=std,
        threshold=threshold,
        score_type=score_type,
        input_shape=EXPECTED_LOGMEL_SHAPE,
        model_sha256=model_hash,
        contract_version=CONTRACT_VERSION,
        contract_sha256=contract_sha256,
        startup_load_ms=elapsed_ms,
        dropout=dropout,
    )
