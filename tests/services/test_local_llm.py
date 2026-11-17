from pathlib import Path
from types import SimpleNamespace

from backend.app.config import AppSettings
from backend.app.services.local_llm import (
    normalize_backend_llm_provider,
    resolve_local_llm_config,
    resolve_ollama_num_ctx,
    resolve_ollama_think,
)


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


def test_resolve_ollama_num_ctx_defaults_to_128k(monkeypatch):
    monkeypatch.delenv("TRANSCIBIO_OLLAMA_NUM_CTX", raising=False)
    assert resolve_ollama_num_ctx() == 131072


def test_resolve_ollama_num_ctx_uses_env_value(monkeypatch):
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_NUM_CTX", "65536")
    assert resolve_ollama_num_ctx() == 65536


def test_resolve_ollama_num_ctx_ignores_invalid_and_clamps_small_values(monkeypatch):
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_NUM_CTX", "lots")
    assert resolve_ollama_num_ctx() == 131072

    monkeypatch.setenv("TRANSCIBIO_OLLAMA_NUM_CTX", "4096")
    assert resolve_ollama_num_ctx() == 16384


def test_resolve_ollama_think_is_off_unless_enabled(monkeypatch):
    monkeypatch.delenv("TRANSCIBIO_OLLAMA_THINK", raising=False)
    assert resolve_ollama_think() is False

    monkeypatch.setenv("TRANSCIBIO_OLLAMA_THINK", "false")
    assert resolve_ollama_think() is False

    monkeypatch.setenv("TRANSCIBIO_OLLAMA_THINK", " True ")
    assert resolve_ollama_think() is True


def test_settings_think_switch_wins_over_env(monkeypatch):
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_THINK", "false")
    store = SimpleNamespace(get_app_setting=lambda key: {"chat": {"think": True}})
    assert resolve_local_llm_config(store=store, settings=make_settings()).think is True

    monkeypatch.setenv("TRANSCIBIO_OLLAMA_THINK", "true")
    store = SimpleNamespace(get_app_setting=lambda key: {"chat": {"think": False}})
    assert resolve_local_llm_config(store=store, settings=make_settings()).think is False


def test_think_defaults_to_env_when_not_saved(monkeypatch):
    store = SimpleNamespace(get_app_setting=lambda key: {"chat": {"model_name": "gemma4:26b"}})
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_THINK", "true")
    assert resolve_local_llm_config(store=store, settings=make_settings()).think is True
    monkeypatch.delenv("TRANSCIBIO_OLLAMA_THINK")
    assert resolve_local_llm_config(store=store, settings=make_settings()).think is False
