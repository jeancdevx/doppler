from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache

import librosa
import numpy as np
import soundfile as sf
from scipy.io import wavfile

from doppler_inference.config import (
    DB_AMIN,
    EXPECTED_LOGMEL_SHAPE,
    FMAX,
    FMIN,
    HOP_SAMPLES,
    HOP_SECONDS,
    N_FFT,
    N_MELS,
    PEAK_TARGET,
    SAMPLE_RATE,
    SILENCE_PEAK,
    STFT_HOP,
    TOP_DB,
    WINDOW_SAMPLES,
    WINDOW_SECONDS,
)
from doppler_inference.schemas import AudioMetadata, ObservationalAudioStats


class AudioValidationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class PreparedAudio:
    metadata: AudioMetadata
    window_starts: list[int]
    logmels: np.ndarray  # shape (W, 64, 94), float32
    short_clip: bool
    short_clip_message: str | None


@lru_cache(maxsize=1)
def get_mel_basis() -> np.ndarray:
    """Banco de filtros Mel Slaney idéntico a 00_preparacion_insumos.ipynb (celda 49)."""
    return librosa.filters.mel(
        sr=SAMPLE_RATE,
        n_fft=N_FFT,
        n_mels=N_MELS,
        fmin=FMIN,
        fmax=FMAX,
        htk=False,
        norm="slaney",
    )


def validate_wav_header(data: bytes) -> None:
    if len(data) < 44:
        raise AudioValidationError(
            code="decode_error",
            message="El archivo está vacío o es demasiado pequeño para ser un WAV válido.",
        )
    if data[:4] not in (b"RIFF", b"RF64") or data[8:12] != b"WAVE":
        raise AudioValidationError(
            code="invalid_format",
            message=(
                "El contenido no corresponde a un archivo WAV válido "
                "(cabecera RIFF/WAVE ausente)."
            ),
        )


def decode_wav_bytes(data: bytes) -> tuple[np.ndarray, int]:
    """Decodifica bytes WAV reproduciendo 00_preparacion_insumos.ipynb (celda 37)."""
    validate_wav_header(data)
    try:
        audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    except Exception:
        try:
            sr, raw = wavfile.read(io.BytesIO(data))
            if raw.dtype == np.uint8:
                audio = (raw.astype(np.float32) - 128.0) / 128.0
            elif np.issubdtype(raw.dtype, np.signedinteger):
                audio = raw.astype(np.float32) / float(2 ** (np.iinfo(raw.dtype).bits - 1))
            elif np.issubdtype(raw.dtype, np.floating):
                audio = raw.astype(np.float32)
            else:
                raise AudioValidationError(
                    code="decode_error",
                    message=f"Codificación WAV no admitida: {raw.dtype}.",
                )
            if audio.ndim == 1:
                audio = audio[:, None]
        except AudioValidationError:
            raise
        except Exception as exc:
            raise AudioValidationError(
                code="decode_error",
                message=(
                    "No se pudo decodificar el archivo WAV. "
                    "Verifica que sea un WAV PCM o flotante íntegro."
                ),
            ) from exc

    if (
        sr <= 0
        or audio.ndim != 2
        or len(audio) == 0
        or audio.shape[1] < 1
        or not np.isfinite(audio).all()
    ):
        raise AudioValidationError(
            code="decode_error",
            message="Audio vacío, con valores no finitos o estructura de canales inválida.",
        )
    return audio, int(sr)


def compute_logmel_window(segment: np.ndarray) -> np.ndarray:
    """Extrae Log-Mel (64, 94) float32 fiel a 00_preparacion_insumos.ipynb (celda 50)."""
    x = np.asarray(segment, dtype=np.float32)
    if len(x) != WINDOW_SAMPLES or not np.isfinite(x).all():
        raise AudioValidationError(
            code="decode_error",
            message="Segmento temporal inválido durante la extracción Log-Mel.",
        )
    mag = np.abs(
        librosa.stft(
            x,
            n_fft=N_FFT,
            hop_length=STFT_HOP,
            win_length=N_FFT,
            window="hann",
            center=True,
            pad_mode="constant",
        )
    )
    power = mag**2
    mel = get_mel_basis() @ power
    logmel = librosa.power_to_db(
        mel,
        ref=np.max,
        amin=DB_AMIN,
        top_db=TOP_DB,
    ).astype(np.float32)
    if logmel.shape != EXPECTED_LOGMEL_SHAPE or not np.isfinite(logmel).all():
        raise AudioValidationError(
            code="inference_error",
            message=f"Forma o valores Log-Mel inesperados: {logmel.shape}.",
        )
    return logmel


def prepare_wav_bytes(data: bytes, max_duration_seconds: float) -> PreparedAudio:
    """Ejecuta el pipeline completo de preparación acústica del contrato Doppler."""
    raw_audio, original_sr = decode_wav_bytes(data)
    original_channels = int(raw_audio.shape[1])
    original_duration = float(len(raw_audio)) / float(original_sr)

    if original_duration > max_duration_seconds:
        raise AudioValidationError(
            code="duration_exceeded",
            message=(
                f"La duración del archivo ({original_duration:.2f} s) supera el límite permitido "
                f"de {max_duration_seconds:.0f} segundos."
            ),
            status_code=422,
        )

    raw_peak = float(np.max(np.abs(raw_audio)))
    raw_mono = raw_audio.mean(axis=1).astype(np.float32)

    # Mediciones estrictamente observacionales previas a la normalización (no alteran la señal)
    rms_before_norm = float(np.sqrt(np.mean(raw_mono.astype(np.float64) ** 2)))
    silence_ratio = float(np.mean(np.abs(raw_mono) <= SILENCE_PEAK))
    clipping_ratio = float(np.mean(np.abs(raw_audio) >= 0.999))

    mono = raw_mono
    if original_sr != SAMPLE_RATE:
        mono = librosa.resample(
            mono,
            orig_sr=original_sr,
            target_sr=SAMPLE_RATE,
            res_type="soxr_hq",
        ).astype(np.float32)

    peak_before = float(np.max(np.abs(mono)))
    if peak_before > 0.0:
        mono = (mono * (PEAK_TARGET / peak_before)).astype(np.float32)

    peak_after = float(np.max(np.abs(mono)))
    rms_after = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
    downmix_cancel = bool(raw_peak > SILENCE_PEAK and peak_before <= SILENCE_PEAK)

    prepared_samples = int(len(mono))
    prepared_duration = prepared_samples / float(SAMPLE_RATE)
    starts = list(range(0, max(0, prepared_samples - WINDOW_SAMPLES + 1), HOP_SAMPLES))

    if not starts:
        observational = ObservationalAudioStats(
            rms_before_normalization=rms_before_norm,
            silence_ratio=silence_ratio,
            clipping_ratio=clipping_ratio,
            logmel_mean=None,
            logmel_std=None,
            spectral_centroid_hz=None,
        )
        metadata = AudioMetadata(
            original_sample_rate=original_sr,
            original_channels=original_channels,
            prepared_sample_rate=SAMPLE_RATE,
            prepared_channels=1,
            duration_seconds=prepared_duration,
            prepared_samples=prepared_samples,
            peak_before_normalization=peak_before,
            peak_after_normalization=peak_after,
            rms_after_normalization=rms_after,
            downmix_cancellation_candidate=downmix_cancel,
            discarded_tail_samples=prepared_samples,
            discarded_tail_seconds=prepared_duration,
            window_seconds=WINDOW_SECONDS,
            hop_seconds=HOP_SECONDS,
            observational=observational,
        )
        return PreparedAudio(
            metadata=metadata,
            window_starts=[],
            logmels=np.empty((0, *EXPECTED_LOGMEL_SHAPE), dtype=np.float32),
            short_clip=True,
            short_clip_message=(
                f"El audio dura {prepared_duration:.2f} s tras remuestreo a 16 000 Hz, "
                f"menos que una ventana completa de {WINDOW_SECONDS:.1f} s. "
                "Conforme al contrato del modelo (drop_short_clip), no se rellena con silencio "
                "ni se emite clasificación."
            ),
        )

    last_end = starts[-1] + WINDOW_SAMPLES
    discarded_tail_samples = max(0, prepared_samples - last_end)
    logmels = np.stack(
        [compute_logmel_window(mono[start : start + WINDOW_SAMPLES]) for start in starts],
        axis=0,
    ).astype(np.float32)

    # Resúmenes observacionales sobre los Log-Mel ya calculados (solo lectura)
    mel_freqs = librosa.mel_frequencies(n_mels=N_MELS, fmin=FMIN, fmax=FMAX, htk=False)
    linear_power = np.power(10.0, logmels.astype(np.float64) / 10.0)
    band_weights = linear_power.mean(axis=(0, 2))
    weight_sum = float(np.sum(band_weights))
    spectral_centroid_hz = (
        float(np.sum(band_weights * mel_freqs) / weight_sum) if weight_sum > 0.0 else 0.0
    )
    observational = ObservationalAudioStats(
        rms_before_normalization=rms_before_norm,
        silence_ratio=silence_ratio,
        clipping_ratio=clipping_ratio,
        logmel_mean=float(np.mean(logmels, dtype=np.float64)),
        logmel_std=float(np.std(logmels, dtype=np.float64)),
        spectral_centroid_hz=spectral_centroid_hz,
    )

    metadata = AudioMetadata(
        original_sample_rate=original_sr,
        original_channels=original_channels,
        prepared_sample_rate=SAMPLE_RATE,
        prepared_channels=1,
        duration_seconds=prepared_duration,
        prepared_samples=prepared_samples,
        peak_before_normalization=peak_before,
        peak_after_normalization=peak_after,
        rms_after_normalization=rms_after,
        downmix_cancellation_candidate=downmix_cancel,
        discarded_tail_samples=discarded_tail_samples,
        discarded_tail_seconds=discarded_tail_samples / float(SAMPLE_RATE),
        window_seconds=WINDOW_SECONDS,
        hop_seconds=HOP_SECONDS,
        observational=observational,
    )
    return PreparedAudio(
        metadata=metadata,
        window_starts=starts,
        logmels=logmels,
        short_clip=False,
        short_clip_message=None,
    )
