from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torchaudio

from backend.app.services.diarization import (
    DiarizationConfigError,
    DiarizationDependencyError,
    DiarizationError,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PYANNOTE_PIPELINE = "pyannote/speaker-diarization-community-1"

HF_MODEL_TERMS_LINKS = {
    "pyannote/speaker-diarization-community-1": [
        "https://huggingface.co/pyannote/speaker-diarization-community-1",
    ]
}

torch.serialization.add_safe_globals([torch.torch_version.TorchVersion])

PYANNOTE_IMPORT_ERROR: Exception | None = None
try:
    from pyannote.audio import Pipeline
except Exception as import_error:
    Pipeline = Any  # type: ignore[misc, assignment]
    PYANNOTE_IMPORT_ERROR = import_error


@dataclass(frozen=True)
class SpeakerSegment:
    start: float
    end: float
    speaker: str


def normalize_hf_token(raw_token: str | None) -> str:
    if not raw_token:
        return ""
    return raw_token.strip().strip('"').strip("'")


def _env_flag_is_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def detect_processing_device(force_gpu: bool | None = None) -> str:
    force_gpu_enabled = _env_flag_is_enabled("FORCE_GPU", default=False)
    if force_gpu is not None:
        force_gpu_enabled = force_gpu

    cuda_available = torch.cuda.is_available()
    if force_gpu_enabled and not cuda_available:
        raise DiarizationConfigError(
            "FORCE_GPU is enabled, but CUDA is not available. "
            "Install CUDA-compatible PyTorch packages and verify NVIDIA driver/CUDA runtime. "
            "To run on CPU, unset FORCE_GPU in your environment/.env."
        )

    return "cuda" if cuda_available else "cpu"


def _safe_pkg_version(package_name: str) -> str:
    try:
        return importlib_metadata.version(package_name)
    except importlib_metadata.PackageNotFoundError:
        return "not installed"
    except Exception:
        return "unknown"


def _get_hf_terms_links(pipeline_name: str) -> list[str]:
    links = HF_MODEL_TERMS_LINKS.get(pipeline_name)
    if links:
        return links
    return HF_MODEL_TERMS_LINKS["pyannote/speaker-diarization-community-1"]


def _build_hf_access_help(pipeline_name: str) -> str:
    links_text = "\n".join(_get_hf_terms_links(pipeline_name))
    return (
        "Use a Hugging Face token with `read` scope from the same account that accepted model terms.\n"
        "Accept user conditions at:\n"
        f"{links_text}\n"
        "After accepting access, restart the app and retry."
    )


def _load_wav_with_wave_module(audio_path: str) -> tuple[torch.Tensor, int]:
    with wave.open(audio_path, "rb") as wav_file:
        num_channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        num_frames = wav_file.getnframes()
        raw_bytes = wav_file.readframes(num_frames)

    if sample_width == 1:
        audio = np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32)
        audio = (audio - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(raw_bytes, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise DiarizationError(f"Unsupported WAV sample width: {sample_width * 8} bit.")

    if num_channels > 1:
        audio = audio.reshape(-1, num_channels).T
    else:
        audio = audio.reshape(1, -1)

    return torch.from_numpy(audio), sample_rate


def _load_wav_audio(audio_path: str) -> tuple[torch.Tensor, int]:
    try:
        return torchaudio.load(audio_path, format="wav")
    except Exception:
        return _load_wav_with_wave_module(audio_path)


def _convert_audio_to_temp_wav(audio_path: str) -> Path:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise DiarizationError("FFmpeg executable not found in PATH.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        temp_wav_path = Path(tmp_file.name)

    command = [
        ffmpeg_path,
        "-y",
        "-loglevel",
        "error",
        "-i",
        audio_path,
        "-vn",
        "-c:a",
        "pcm_s16le",
        str(temp_wav_path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except OSError as exc:
        temp_wav_path.unlink(missing_ok=True)
        raise DiarizationError(
            f"Failed to run FFmpeg for diarization audio fallback: {exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        temp_wav_path.unlink(missing_ok=True)
        raise DiarizationError("FFmpeg timed out while converting audio for diarization.") from exc

    if result.returncode != 0 or not temp_wav_path.exists():
        temp_wav_path.unlink(missing_ok=True)
        stderr = (result.stderr or "").strip()
        raise DiarizationError(stderr or "FFmpeg failed to convert audio for diarization.")

    return temp_wav_path


def _build_pyannote_audio_input(audio_path: str) -> dict[str, Any]:
    try:
        waveform, sample_rate = torchaudio.load(audio_path)
    except Exception as first_error:
        temp_wav_path: Path | None = None
        try:
            if Path(audio_path).suffix.lower() == ".wav":
                waveform, sample_rate = _load_wav_audio(audio_path)
            else:
                temp_wav_path = _convert_audio_to_temp_wav(audio_path)
                waveform, sample_rate = _load_wav_audio(str(temp_wav_path))
        except Exception as fallback_error:
            raise DiarizationError(
                f"Failed to decode audio file '{audio_path}' with torchaudio and WAV fallback. "
                f"First error: {first_error}; fallback error: {fallback_error}"
            ) from fallback_error
        finally:
            if temp_wav_path is not None:
                temp_wav_path.unlink(missing_ok=True)

    if waveform.ndim == 1:
        waveform = waveform.unsqueeze(0)
    return {"waveform": waveform, "sample_rate": sample_rate}


def _extract_speaker_segments(diarization_result: Any) -> list[SpeakerSegment]:
    annotation = None
    if hasattr(diarization_result, "exclusive_speaker_diarization"):
        annotation = diarization_result.exclusive_speaker_diarization
    elif hasattr(diarization_result, "speaker_diarization"):
        annotation = diarization_result.speaker_diarization
    elif hasattr(diarization_result, "itertracks"):
        annotation = diarization_result

    if annotation is not None and hasattr(annotation, "itertracks"):
        segments: list[SpeakerSegment] = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            segments.append(
                SpeakerSegment(
                    start=float(turn.start),
                    end=float(turn.end),
                    speaker=str(speaker),
                )
            )
        return segments

    serialized = None
    if hasattr(diarization_result, "serialize"):
        try:
            serialized = diarization_result.serialize()
        except Exception:
            serialized = None
    elif isinstance(diarization_result, dict):
        serialized = diarization_result

    if isinstance(serialized, dict):
        for key in ("exclusive_diarization", "diarization", "speaker_diarization"):
            items = serialized.get(key)
            if not isinstance(items, list):
                continue
            segments = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                start = item.get("start")
                end = item.get("end")
                speaker = item.get("speaker", "UNKNOWN_SPEAKER")
                if start is None or end is None:
                    continue
                segments.append(
                    SpeakerSegment(
                        start=float(start),
                        end=float(end),
                        speaker=str(speaker),
                    )
                )
            return segments

    raise DiarizationError(
        f"Unsupported diarization output type: {type(diarization_result).__name__}"
    )


@lru_cache(maxsize=8)
def _load_pipeline(pipeline_name: str, token: str, device: str) -> Any:
    if PYANNOTE_IMPORT_ERROR is not None:
        torch_version = _safe_pkg_version("torch")
        torchvision_version = _safe_pkg_version("torchvision")
        torchaudio_version = _safe_pkg_version("torchaudio")
        raise DiarizationDependencyError(
            "Could not import pyannote.audio.\n"
            f"Import error: {PYANNOTE_IMPORT_ERROR}\n"
            f"Detected versions: torch={torch_version}, torchvision={torchvision_version}, "
            f"torchaudio={torchaudio_version}"
        )

    try:
        _LOGGER.info("[Diarization] Loading pipeline '%s' on %s...", pipeline_name, device.upper())
        try:
            pipeline = Pipeline.from_pretrained(pipeline_name, token=token)
        except TypeError:
            pipeline = Pipeline.from_pretrained(pipeline_name, use_auth_token=token)
    except Exception as exc:
        help_text = _build_hf_access_help(pipeline_name)
        raise DiarizationError(
            f"Error loading diarization pipeline '{pipeline_name}': {exc}\n{help_text}"
        ) from exc

    if pipeline is None:
        help_text = _build_hf_access_help(pipeline_name)
        raise DiarizationError(f"Pipeline returned None.\n{help_text}")

    pipeline.to(torch.device(device))
    _LOGGER.info("[Diarization] Pipeline loaded.")
    return pipeline


class PyannoteDiarizer:
    def __init__(
        self,
        pipeline_name: str = DEFAULT_PYANNOTE_PIPELINE,
        device: str | None = None,
    ) -> None:
        self.pipeline_name = pipeline_name
        self.device = device or detect_processing_device()

    def diarize(
        self,
        audio_path: str,
        auth_token: str | None = None,
    ) -> list[SpeakerSegment]:
        token = normalize_hf_token(auth_token or os.environ.get("HF_TOKEN"))
        if not token:
            raise DiarizationConfigError("No HF token found. Provide a Hugging Face token.")

        _LOGGER.info("[Diarization] Starting diarization.")
        os.environ["HF_TOKEN"] = token
        pipeline = _load_pipeline(self.pipeline_name, token, self.device)
        audio_input = _build_pyannote_audio_input(audio_path)

        try:
            diarization_result = pipeline(audio_input)
            segments = _extract_speaker_segments(diarization_result)
            _LOGGER.info("[Diarization] Diarization complete (%d segments).", len(segments))
            return segments
        except Exception as exc:
            raise DiarizationError(
                f"Error during diarization: {exc}. "
                "If this mentions AudioDecoder/torchcodec, verify the audio file is valid. "
                "For MP3 uploads, ensure FFmpeg is installed."
            ) from exc
