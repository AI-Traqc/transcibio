from pathlib import Path
from types import SimpleNamespace

from backend.app.config import AppSettings
from backend.app.services.local_llm import normalize_backend_llm_provider, resolve_local_llm_config


def make_settings(*, llm_provider: str = "lmstudio") -> AppSettings:
    root = Path.cwd()
    return AppSettings(
        app_name="Transcibio API",
        environment="test",
        host="127.0.0.1",
        port=8000,
        data_root=root / "data",
        db_path=root / "data" / "privata.db",
        sessions_root=root / "data" / "sessions",
        processing_profile="balanced",
        stt_provider="faster-whisper",
        llm_provider=llm_provider,
        tts_provider="piper",
        ffmpeg_required=False,
    )


def test_normalize_backend_llm_provider_coerces_to_ollama():
    assert normalize_backend_llm_provider("lmstudio") == "ollama"
    assert normalize_backend_llm_provider("ollama") == "ollama"
    assert normalize_backend_llm_provider("none") == "ollama"


def test_resolve_local_llm_config_prefers_persisted_ollama_model_name():
    store = SimpleNamespace(
        get_app_setting=lambda key: {"chat": {"llm_provider": "ollama", "model_name": "qwen2.5:7b"}}
    )

    resolved = resolve_local_llm_config(
        store=store, settings=make_settings(llm_provider="lmstudio")
    )

    assert resolved.provider == "ollama"
    assert resolved.model_name == "qwen2.5:7b"


def test_resolve_local_llm_config_coerces_none_to_ollama():
    store = SimpleNamespace(
        get_app_setting=lambda key: {"chat": {"llm_provider": "none", "model_name": ""}}
    )

    resolved = resolve_local_llm_config(store=store, settings=make_settings(llm_provider="ollama"))

    assert resolved.provider == "ollama"
    assert resolved.model_name == "gpt-oss-20b"
