from pathlib import Path

from backend.app.config import AppSettings
from backend.app.services.app_context import build_app_context
from backend.app.store import SQLiteStore


def _setup(tmp_path: Path, saved: dict | None = None) -> tuple[SQLiteStore, AppSettings]:
    settings = AppSettings(
        app_name="Transcibio Test",
        environment="test",
        host="127.0.0.1",
        port=8000,
        data_root=tmp_path,
        db_path=tmp_path / "t.db",
        sessions_root=tmp_path / "sessions",
        processing_profile="balanced",
        stt_provider="faster-whisper",
        llm_provider="ollama",
        tts_provider="piper",
        ffmpeg_required=False,
    )
    store = SQLiteStore(settings.db_path)
    store.initialize()
    if saved:
        store.set_app_setting("privata_vnext_settings", saved)
    return store, settings


def test_describes_the_whisper_setup_in_english(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TRANSCIBIO_OLLAMA_THINK", raising=False)
    store, settings = _setup(tmp_path, {"chat": {"model_name": "gemma4:26b"}})
    text = build_app_context(store, settings, language="en")
    assert "Transcibio" in text and "runs entirely on this device" in text
    assert 'faster-whisper "medium"' in text and "pyannote" in text
    assert 'voice input with Whisper (faster-whisper "small")' in text
    assert "gemma4:26b" in text and "thinking mode off" in text
    assert "Piper" in text


def test_follows_settings_nemotron_quality_kokoro_in_german(tmp_path: Path):
    saved = {
        "stt": {"engine": "nemotron", "default_preset": "quality"},
        "chat": {"model_name": "qwen3:32b", "think": True},
        "tts": {"voice_engine": "kokoro"},
    }
    store, settings = _setup(tmp_path, saved)
    text = build_app_context(store, settings, language="de")
    assert text.startswith("Über Transcibio")
    assert "Transkription mit NVIDIA Nemotron 3.5 Transcribe" in text
    assert "Spracheingabe mit NVIDIA Nemotron 3.5 Transcribe" in text
    assert "qwen3:32b" in text and "Denkmodus an" in text
    assert "Kokoro" in text


def test_voice_turn_engine_overrides_the_stored_voice(tmp_path: Path):
    store, settings = _setup(tmp_path, {"tts": {"voice_engine": "piper"}})
    assert "Kokoro" in build_app_context(store, settings, language="en", voice_engine="kokoro")
