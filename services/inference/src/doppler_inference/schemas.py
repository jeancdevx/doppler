from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WindowPrediction(BaseModel):
    index: int = Field(ge=0)
    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(gt=0.0)
    score: float = Field(ge=0.0, le=1.0)
    label: Literal["EMERGENCY", "NON_EMERGENCY"]
    margin_vs_threshold: float


class AudioMetadata(BaseModel):
    original_sample_rate: int = Field(gt=0)
    original_channels: int = Field(ge=1)
    prepared_sample_rate: int = Field(gt=0)
    prepared_channels: int = Field(ge=1)
    duration_seconds: float = Field(gt=0.0)
    prepared_samples: int = Field(gt=0)
    peak_before_normalization: float = Field(ge=0.0)
    peak_after_normalization: float = Field(ge=0.0)
    rms_after_normalization: float = Field(ge=0.0)
    downmix_cancellation_candidate: bool
    discarded_tail_samples: int = Field(ge=0)
    discarded_tail_seconds: float = Field(ge=0.0)
    window_seconds: float = Field(gt=0.0)
    hop_seconds: float = Field(gt=0.0)


class StageTimings(BaseModel):
    decode_and_prepare_ms: float = Field(ge=0.0)
    inference_ms: float = Field(ge=0.0)
    total_ms: float = Field(ge=0.0)


class InferResponse(BaseModel):
    audio_sha256: str
    model_sha256: str
    contract_version: str
    contract_sha256: str
    threshold: float
    score_type: str
    positive_class: Literal["EMERGENCY"] = "EMERGENCY"
    negative_class: Literal["NON_EMERGENCY"] = "NON_EMERGENCY"
    audio: AudioMetadata
    windows: list[WindowPrediction]
    windows_total: int = Field(ge=0)
    windows_positive: int = Field(ge=0)
    timings: StageTimings
    short_clip: bool = False
    short_clip_message: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    ready: bool
    model_loaded: bool
    model_sha256: str | None = None
    contract_version: str
    contract_sha256: str | None = None
    threshold: float | None = None
    score_type: str | None = None
    input_shape: list[int] | None = None
    torch_version: str
    torch_num_threads: int
    startup_load_ms: float | None = None
