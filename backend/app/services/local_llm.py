from __future__ import annotations

import os
from dataclasses import dataclass

from backend.app.config import AppSettings
from backend.app.store import SQLiteStore

_SETTINGS_KEY = "privata_vnext_settings"
_DEFAULT_OLLAMA_MODEL = "gpt-oss-20b"


@dataclass(frozen=True)
class LocalLlmConfig:
    provider: str
    model_name: str


def normalize_backend_llm_provider(raw: str | None) -> str:
    return "ollama"


def resolve_local_llm_config(*, store: SQLiteStore, settings: AppSettings) -> LocalLlmConfig:
    provider = normalize_backend_llm_provider(settings.llm_provider)
    model_name = ""

    persisted = store.get_app_setting(_SETTINGS_KEY) or {}
    if isinstance(persisted, dict):
        chat = persisted.get("chat")
        if isinstance(chat, dict):
            provider = normalize_backend_llm_provider(str(chat.get("llm_provider") or provider))
            raw_model_name = chat.get("model_name")
            if isinstance(raw_model_name, str):
                model_name = raw_model_name.strip()

    return LocalLlmConfig(
        provider="ollama",
        model_name=model_name or os.getenv("TRANSCIBIO_OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL),
    )
