import io
from pathlib import Path

import pytest

from backend.app.config import AppSettings
from backend.app.services.audio_storage import (
    AudioProbeMetadata,
    AudioStorageService,
    AudioValidationError,
)


def make_settings(root: Path) -> AppSettings:
    return AppSettings(
        app_name="Transcibio API",
        environment="test",
        host="127.0.0.1",
        port=8000,
        data_root=root,
        db_path=root / "privata.db",
        sessions_root=root / "sessions",
        processing_profile="balanced",
        stt_provider="faster-whisper",
        llm_provider="ollama",
        tts_provider="piper",
        ffmpeg_required=False,
    )


class FakeProbeStorageService(AudioStorageService):
    """Skips ffprobe so the MIME/extension validation can be tested without FFmpeg."""

    def probe_audio(self, audio_path: Path) -> AudioProbeMetadata:
        return AudioProbeMetadata(duration_ms=1000, sample_rate_hz=16000, channels=1)


def _upload(service: AudioStorageService, filename: str, content_type: str | None):
    return service.save_meeting_upload(
        session_id="s1",
        filename=filename,
        content_type=content_type,
        fileobj=io.BytesIO(b"RIFF....WAVE"),
    )


@pytest.mark.parametrize(
    "content_type",
    ["audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave", "application/octet-stream", None],
)
def test_wav_upload_accepts_browser_mime_types(tmp_path, content_type):
    # Ubuntu 24.04 / GNOME report WAV as audio/vnd.wave.
    stored = _upload(FakeProbeStorageService(make_settings(tmp_path)), "call.wav", content_type)
    assert stored.absolute_path.exists()
    assert stored.stored_filename.endswith(".wav")


def test_upload_rejects_unrelated_mime_type(tmp_path):
    with pytest.raises(AudioValidationError):
        _upload(FakeProbeStorageService(make_settings(tmp_path)), "call.wav", "video/mp4")


def test_upload_rejects_unsupported_extension(tmp_path):
    with pytest.raises(AudioValidationError):
        _upload(FakeProbeStorageService(make_settings(tmp_path)), "call.flac", "audio/flac")
