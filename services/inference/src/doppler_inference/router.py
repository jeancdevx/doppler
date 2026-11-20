from __future__ import annotations

from typing import Annotated

import torch
from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from doppler_inference.audio import AudioValidationError
from doppler_inference.config import CONTRACT_VERSION
from doppler_inference.schemas import HealthResponse, InferResponse
from doppler_inference.service import InferenceEngine

router = APIRouter(tags=["inference"])


def get_engine(request: Request) -> InferenceEngine:
    engine: InferenceEngine | None = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "model_not_ready", "message": "El modelo aún no está cargado."},
        )
    return engine


EngineDep = Annotated[InferenceEngine, Depends(get_engine)]


@router.get("/health")
def health(request: Request) -> HealthResponse:
    engine: InferenceEngine | None = getattr(request.app.state, "engine", None)
    if engine is None:
        return HealthResponse(
            status="degraded",
            ready=False,
            model_loaded=False,
            contract_version=CONTRACT_VERSION,
            torch_version=torch.__version__,
            torch_num_threads=torch.get_num_threads(),
        )
    bundle = engine.bundle
    return HealthResponse(
        status="ok",
        ready=True,
        model_loaded=True,
        model_sha256=bundle.model_sha256,
        contract_version=bundle.contract_version,
        contract_sha256=bundle.contract_sha256,
        threshold=bundle.threshold,
        score_type=bundle.score_type,
        input_shape=list(bundle.input_shape),
        torch_version=torch.__version__,
        torch_num_threads=torch.get_num_threads(),
        startup_load_ms=round(bundle.startup_load_ms, 3),
    )


@router.get("/ready")
def ready(engine: EngineDep) -> HealthResponse:
    bundle = engine.bundle
    return HealthResponse(
        status="ok",
        ready=True,
        model_loaded=True,
        model_sha256=bundle.model_sha256,
        contract_version=bundle.contract_version,
        contract_sha256=bundle.contract_sha256,
        threshold=bundle.threshold,
        score_type=bundle.score_type,
        input_shape=list(bundle.input_shape),
        torch_version=torch.__version__,
        torch_num_threads=torch.get_num_threads(),
        startup_load_ms=round(bundle.startup_load_ms, 3),
    )


@router.post("/infer")
async def infer_audio(
    request: Request,
    engine: EngineDep,
) -> InferResponse:
    payload = await request.body()
    if len(payload) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "decode_error", "message": "El cuerpo de audio recibido está vacío."},
        )
    if len(payload) > engine.settings.max_file_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "size_exceeded",
                "message": (
                    f"El archivo ({len(payload)} bytes) excede el límite de "
                    f"{engine.settings.max_file_bytes} bytes."
                ),
            },
        )
    try:
        return await run_in_threadpool(engine.infer_wav_bytes, payload)
    except AudioValidationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "inference_error",
                "message": "Error interno al ejecutar el pipeline de inferencia acústica.",
            },
        ) from exc
