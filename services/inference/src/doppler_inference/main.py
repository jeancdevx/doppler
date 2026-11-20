from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI

from doppler_inference.audio import compute_logmel_window, get_mel_basis
from doppler_inference.config import WINDOW_SAMPLES, InferenceSettings
from doppler_inference.model import load_model_bundle
from doppler_inference.router import router
from doppler_inference.service import InferenceEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("doppler_inference")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = InferenceSettings.from_env()
    logger.info(
        "Cargando checkpoint Doppler ResNet18 en CPU (hilos=%d) desde %s",
        settings.torch_num_threads,
        settings.model_path,
    )
    bundle = load_model_bundle(
        model_path=settings.model_path,
        inference_config_path=settings.inference_config_path,
        torch_num_threads=settings.torch_num_threads,
    )
    # Precompila filtros Mel y kernels STFT/librosa al arranque para evitar penalizar la primera petición
    get_mel_basis()
    compute_logmel_window(np.zeros(WINDOW_SAMPLES, dtype=np.float32))
    app.state.engine = InferenceEngine(bundle=bundle, settings=settings)
    logger.info(
        "Modelo listo en %.2f ms | sha256=%s | threshold=%.16f",
        bundle.startup_load_ms,
        bundle.model_sha256[:16],
        bundle.threshold,
    )
    yield
    app.state.engine = None


app = FastAPI(
    title="Doppler Inference Internal Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)
app.include_router(router)
