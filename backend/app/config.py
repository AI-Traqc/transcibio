from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

ProfileName = Literal["fast", "balanced", "quality"]


class RuntimeConfigError(RuntimeError):
    """Raised when local runtime prerequisites are not met."""


@dataclass(frozen=True)
class AppSettings:
    app_name: str
    environment: str
    host: str
    port: int
    data_root: Path
    db_path: Path
    sessions_root: Path
    processing_profile: ProfileName
    stt_provider: str
    llm_provider: str
    tts_provider: str
    ffmpeg_required: bool


def _getenv(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value is not None else default


def _getenv_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeConfigError(f"Environment variable {name} must be an integer.") from exc


def _getenv_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _getenv_profile(name: str, default: ProfileName) -> ProfileName:
    raw = _getenv(name, default).lower()
    if raw not in {"fast", "balanced", "quality"}:
        raise RuntimeConfigError(
            f"Environment variable {name} must be one of: fast, balanced, quality."
        )
    return raw  # type: ignore[return-value]


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (Path.cwd() / path)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    # Keep parity with Streamlit app startup: load local .env into process env.
    # Existing environment variables still win (override=False).
    load_dotenv(override=False)
    data_root = _resolve_path(_getenv("TRANSCIBIO_DATA_ROOT", "data"))
    db_path = _resolve_path(_getenv("TRANSCIBIO_DB_PATH", str(data_root / "privata.db")))
    sessions_root = _resolve_path(_getenv("TRANSCIBIO_SESSIONS_ROOT", str(data_root / "sessions")))
    return AppSettings(
        app_name=_getenv("TRANSCIBIO_APP_NAME", "Transcibio API"),
        environment=_getenv("TRANSCIBIO_ENV", "development"),
        host=_getenv("TRANSCIBIO_API_HOST", "127.0.0.1"),
        port=_getenv_int("TRANSCIBIO_API_PORT", 8000),
        data_root=data_root,
        db_path=db_path,
        sessions_root=sessions_root,
        processing_profile=_getenv_profile("TRANSCIBIO_PROFILE", "balanced"),
        stt_provider=_getenv("TRANSCIBIO_STT_PROVIDER", "faster-whisper"),
        llm_provider=_getenv("TRANSCIBIO_LLM_PROVIDER", "ollama"),
        tts_provider=_getenv("TRANSCIBIO_TTS_PROVIDER", "piper"),
        ffmpeg_required=_getenv_bool("TRANSCIBIO_REQUIRE_FFMPEG", False),
    )


def ensure_runtime_directories(settings: AppSettings) -> None:
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.sessions_root.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)


def detect_ffmpeg() -> dict[str, str | bool]:
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    return {
        "available": bool(ffmpeg_path and ffprobe_path),
        "ffmpeg_path": ffmpeg_path or "",
        "ffprobe_path": ffprobe_path or "",
    }


def initialize_runtime(settings: AppSettings) -> dict[str, object]:
    ensure_runtime_directories(settings)
    ffmpeg = detect_ffmpeg()
    if settings.ffmpeg_required and not ffmpeg["available"]:
        raise RuntimeConfigError(
            "FFmpeg is required but was not found in PATH. Install ffmpeg and ffprobe."
        )
    return {
        "ffmpeg": ffmpeg,
        "paths": {
            "data_root": str(settings.data_root),
            "db_path": str(settings.db_path),
            "sessions_root": str(settings.sessions_root),
        },
        "providers": {
            "stt": settings.stt_provider,
            "llm": settings.llm_provider,
            "tts": settings.tts_provider,
        },
        "profile": settings.processing_profile,
    }
