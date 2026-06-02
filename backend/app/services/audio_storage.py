from __future__ import annotations

import mimetypes
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from backend.app.config import AppSettings

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav"}
ALLOWED_AUDIO_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
}
ALLOWED_RECORDING_EXTENSIONS = {".webm", ".ogg", ".wav", ".mp3", ".m4a", ".mp4"}
MIME_TO_EXTENSION = {
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "audio/ogg": ".ogg",
    "application/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
}


class AudioStorageError(RuntimeError):
    """Base error for local audio storage/probing."""


class AudioValidationError(AudioStorageError):
    """Raised for invalid upload type or malformed metadata."""


class AudioProbeError(AudioStorageError):
    """Raised when ffprobe cannot read audio metadata."""


class AudioConversionError(AudioStorageError):
    """Raised when ffmpeg conversion/normalization fails."""


@dataclass(frozen=True)
class AudioProbeMetadata:
    duration_ms: int
    sample_rate_hz: int | None
    channels: int | None


@dataclass(frozen=True)
class StoredAudioUpload:
    absolute_path: Path
    relative_path: str
    original_filename: str
    stored_filename: str
    mime_type: str
    duration_ms: int
    sample_rate_hz: int | None
    channels: int | None


def _sanitize_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "upload"
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return sanitized[:180] or "upload"


def _detect_mime_type(filename: str, content_type: str | None) -> str:
    if content_type:
        return content_type.strip().lower()
    guessed, _ = mimetypes.guess_type(filename)
    return (guessed or "application/octet-stream").lower()


def _extract_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


class AudioStorageService:
    def __init__(
        self,
        settings: AppSettings,
        *,
        ffmpeg_path: str | None = None,
        ffprobe_path: str | None = None,
    ) -> None:
        self._settings = settings
        self._ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
        self._ffprobe_path = ffprobe_path or shutil.which("ffprobe") or "ffprobe"

    def save_meeting_upload(
        self,
        *,
        session_id: str,
        filename: str,
        content_type: str | None,
        fileobj: BinaryIO,
    ) -> StoredAudioUpload:
        sanitized_name = _sanitize_filename(filename)
        extension = _extract_extension(sanitized_name)
        if extension not in ALLOWED_AUDIO_EXTENSIONS:
            raise AudioValidationError(
                "Unsupported audio file type. Only .mp3 and .wav are allowed."
            )

        mime_type = _detect_mime_type(sanitized_name, content_type)
        if mime_type not in ALLOWED_AUDIO_MIME_TYPES and mime_type != "application/octet-stream":
            raise AudioValidationError(f"Unsupported MIME type: {mime_type}")

        target_dir = self._settings.sessions_root / session_id / "audio"
        target_dir.mkdir(parents=True, exist_ok=True)

        unique_name = f"meeting_{uuid4().hex}{extension}"
        absolute_path = target_dir / unique_name

        self._write_stream(fileobj, absolute_path)
        try:
            metadata = self.probe_audio(absolute_path)
        except Exception:
            absolute_path.unlink(missing_ok=True)
            raise
        relative_path = os.path.relpath(absolute_path, self._settings.data_root)

        return StoredAudioUpload(
            absolute_path=absolute_path,
            relative_path=relative_path.replace("\\", "/"),
            original_filename=sanitized_name,
            stored_filename=unique_name,
            mime_type=mime_type
            if mime_type != "application/octet-stream"
            else self._mime_from_ext(extension),
            duration_ms=metadata.duration_ms,
            sample_rate_hz=metadata.sample_rate_hz,
            channels=metadata.channels,
        )

    def save_recording_upload(
        self,
        *,
        session_id: str,
        filename: str,
        content_type: str | None,
        fileobj: BinaryIO,
        max_duration_ms: int = 15 * 60 * 1000,
        normalize_sample_rate_hz: int = 16000,
    ) -> StoredAudioUpload:
        target_dir = self._settings.sessions_root / session_id / "audio"
        target_dir.mkdir(parents=True, exist_ok=True)

        sanitized_name = _sanitize_filename(filename or "recording")
        mime_type = _detect_mime_type(sanitized_name, content_type)
        extension = self._resolve_recording_extension(sanitized_name, mime_type)

        if extension not in ALLOWED_RECORDING_EXTENSIONS:
            raise AudioValidationError("Unsupported recording format.")

        raw_name = f"recording_raw_{uuid4().hex}{extension}"
        raw_path = target_dir / raw_name
        normalized_name = f"meeting_recording_{uuid4().hex}.wav"
        normalized_path = target_dir / normalized_name

        self._write_stream(fileobj, raw_path)
        try:
            raw_meta = self.probe_audio(raw_path)
            if raw_meta.duration_ms > max_duration_ms:
                raise AudioValidationError("Recording exceeds maximum duration of 15 minutes.")

            self._convert_to_normalized_wav(
                input_path=raw_path,
                output_path=normalized_path,
                sample_rate_hz=normalize_sample_rate_hz,
            )
            normalized_meta = self.probe_audio(normalized_path)
        except Exception:
            raw_path.unlink(missing_ok=True)
            normalized_path.unlink(missing_ok=True)
            raise
        else:
            raw_path.unlink(missing_ok=True)

        relative_path = os.path.relpath(normalized_path, self._settings.data_root)
        return StoredAudioUpload(
            absolute_path=normalized_path,
            relative_path=relative_path.replace("\\", "/"),
            original_filename=sanitized_name,
            stored_filename=normalized_name,
            mime_type="audio/wav",
            duration_ms=normalized_meta.duration_ms,
            sample_rate_hz=normalized_meta.sample_rate_hz,
            channels=normalized_meta.channels,
        )

    def _write_stream(self, fileobj: BinaryIO, destination: Path) -> None:
        with destination.open("wb") as out:
            while True:
                chunk = fileobj.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

    def _resolve_recording_extension(self, filename: str, mime_type: str) -> str:
        extension = _extract_extension(filename)
        if extension:
            return extension
        return MIME_TO_EXTENSION.get(mime_type, ".webm")

    @staticmethod
    def _mime_from_ext(extension: str) -> str:
        return "audio/mpeg" if extension == ".mp3" else "audio/wav"

    def _convert_to_normalized_wav(
        self,
        *,
        input_path: Path,
        output_path: Path,
        sample_rate_hz: int,
    ) -> None:
        command = [
            self._ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate_hz),
            "-c:a",
            "pcm_s16le",
            str(output_path),
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
            raise AudioConversionError(f"Failed to run ffmpeg: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AudioConversionError("ffmpeg timed out while converting recording.") from exc

        if result.returncode != 0 or not output_path.exists():
            raise AudioConversionError(result.stderr.strip() or "ffmpeg conversion failed.")

    def probe_audio(self, audio_path: Path) -> AudioProbeMetadata:
        command = [
            self._ffprobe_path,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(audio_path),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except OSError as exc:
            raise AudioProbeError(f"Failed to run ffprobe: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AudioProbeError("ffprobe timed out while probing audio file.") from exc

        if result.returncode != 0:
            raise AudioProbeError(result.stderr.strip() or "ffprobe failed to read audio file.")

        try:
            import json

            payload = json.loads(result.stdout or "{}")
        except Exception as exc:  # pragma: no cover - defensive parsing
            raise AudioProbeError("Unable to parse ffprobe output.") from exc

        format_info = payload.get("format") or {}
        streams = payload.get("streams") or []
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        duration_seconds = format_info.get("duration")
        if duration_seconds is None and audio_stream is not None:
            duration_seconds = audio_stream.get("duration")
        if duration_seconds is None:
            duration_seconds = self._probe_duration_fallback(audio_path)
            if duration_seconds is None:
                raise AudioProbeError("Could not determine audio duration.")

        try:
            duration_ms = int(round(float(duration_seconds) * 1000))
        except (TypeError, ValueError) as exc:
            raise AudioProbeError("Invalid audio duration returned by ffprobe.") from exc

        sample_rate_hz: int | None = None
        channels: int | None = None
        if audio_stream is not None:
            try:
                if audio_stream.get("sample_rate") is not None:
                    sample_rate_hz = int(audio_stream["sample_rate"])
            except (TypeError, ValueError):
                sample_rate_hz = None
            try:
                if audio_stream.get("channels") is not None:
                    channels = int(audio_stream["channels"])
            except (TypeError, ValueError):
                channels = None

        return AudioProbeMetadata(
            duration_ms=max(duration_ms, 0),
            sample_rate_hz=sample_rate_hz,
            channels=channels,
        )

    def _probe_duration_fallback(self, audio_path: Path) -> str | None:
        """Decode audio through ffmpeg to determine duration when metadata is missing."""
        command = [
            self._ffmpeg_path,
            "-i",
            str(audio_path),
            "-f",
            "null",
            "-" if os.name != "nt" else "NUL",
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        match = re.findall(r"time=(\d+):(\d+):(\d+)\.(\d+)", result.stderr or "")
        if not match:
            return None
        hours, minutes, seconds, centiseconds = match[-1]
        total = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(centiseconds) / 100
        return str(total) if total > 0 else None
