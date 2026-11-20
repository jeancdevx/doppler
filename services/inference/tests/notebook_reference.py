from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch
from torch import nn
from torchvision.models import resnet18

NB_CFG = {
    "sample_rate": 16000,
    "window_seconds": 3.0,
    "hop_seconds": 1.5,
    "peak_target": 0.99,
    "n_fft": 2048,
    "stft_hop": 512,
    "n_mels": 64,
    "fmin": 20.0,
    "fmax": 8000.0,
    "db_amin": 1e-10,
    "top_db": 80.0,
}

SR = NB_CFG["sample_rate"]
N = int(round(NB_CFG["window_seconds"] * SR))
H = int(round(NB_CFG["hop_seconds"] * SR))

NB_MEL_BASIS = librosa.filters.mel(
    sr=SR,
    n_fft=NB_CFG["n_fft"],
    n_mels=NB_CFG["n_mels"],
    fmin=NB_CFG["fmin"],
    fmax=NB_CFG["fmax"],
    htk=False,
    norm="slaney",
)


class NotebookVisualTransfer(nn.Module):
    def __init__(self, dropout: float) -> None:
        super().__init__()
        self.net = resnet18(weights=None)
        self.net.fc = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(self.net.fc.in_features, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x.repeat(1, 3, 1, 1)).squeeze(1)


def nb_harmonize(path: Path) -> np.ndarray:
    a, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = a.mean(axis=1).astype(np.float32)
    if sr != SR:
        mono = librosa.resample(mono, orig_sr=sr, target_sr=SR, res_type="soxr_hq")
    peak = float(np.max(np.abs(mono)))
    if peak > 0:
        mono = mono * (NB_CFG["peak_target"] / peak)
    return mono


def nb_extract_logmels(path: Path) -> tuple[list[int], list[np.ndarray]]:
    mono = nb_harmonize(path)
    starts = list(range(0, max(0, len(mono) - N + 1), H))
    out: list[np.ndarray] = []
    for start in starts:
        x = np.asarray(mono[start : start + N], dtype=np.float32)
        mag = np.abs(
            librosa.stft(
                x,
                n_fft=NB_CFG["n_fft"],
                hop_length=NB_CFG["stft_hop"],
                win_length=NB_CFG["n_fft"],
                window="hann",
                center=True,
                pad_mode="constant",
            )
        )
        power = mag**2
        mel = NB_MEL_BASIS @ power
        logmel = librosa.power_to_db(
            mel,
            ref=np.max,
            amin=NB_CFG["db_amin"],
            top_db=NB_CFG["top_db"],
        ).astype(np.float32)
        out.append(logmel)
    return starts, out


def nb_load_and_score(
    model_path: Path, wav_path: Path
) -> dict[str, object]:
    artifact = torch.load(model_path, map_location="cpu", weights_only=True)
    model = NotebookVisualTransfer(artifact["params"]["dropout"])
    model.load_state_dict(artifact["state_dict"], strict=True)
    model.eval()
    mean = np.asarray(artifact["normalization_mean"], dtype=np.float32)
    std = np.asarray(artifact["normalization_std"], dtype=np.float32)
    threshold = float(artifact["threshold"])

    starts, logmels = nb_extract_logmels(wav_path)
    scores: list[float] = []
    labels: list[str] = []
    with torch.inference_mode():
        for lm in logmels:
            norm = (lm - mean[:, None]) / std[:, None]
            tensor = torch.from_numpy(norm[None, None].astype(np.float32))
            logits = model(tensor)
            score = float(torch.sigmoid(logits.float()).cpu().numpy()[0])
            scores.append(score)
            labels.append("EMERGENCY" if score >= threshold else "NON_EMERGENCY")
    return {
        "starts": starts,
        "logmels": logmels,
        "scores": scores,
        "labels": labels,
        "threshold": threshold,
    }
