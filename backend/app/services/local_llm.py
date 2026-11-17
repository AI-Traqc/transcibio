from __future__ import annotations

import os
from dataclasses import dataclass

from backend.app.config import AppSettings
from backend.app.store import SQLiteStore

_SETTINGS_KEY = "privata_vnext_settings"
_DEFAULT_OLLAMA_MODEL = "gpt-oss-20b"

# One context size for every Ollama call (chat, voice, titles, correction): Ollama reloads the
# model whenever a request asks for a different num_ctx (17-35 s at 128k on a GB10), and a
# request without num_ctx gets Ollama's own default (on a GB10 the model's full 262144).
# 128k costs gemma4:26b only a few GB of KV cache (sliding-window attention); Ollama clamps
# the value to the model's trained context. Lower it via env on small GPUs.
_DEFAULT_OLLAMA_NUM_CTX = 131072
# Chat needs room for the retrieval context plus the reserved prompt and answer tokens.
_MIN_OLLAMA_NUM_CTX = 16384


_TRUTHY = frozenset({"1", "true", "yes", "on"})


def resolve_ollama_think() -> bool:
    """Default for reasoning ("thinking") in typed chat and transcript correction.

    The Settings switch (`chat.think`, see `resolve_local_llm_config`) wins; this env value
    (`TRANSCIBIO_OLLAMA_THINK`) is only the default when nothing was saved. Off sends
    `think: false`, which every model accepts (verified on granite4:3b, which can't think);
    on sends no `think` field, so each model uses its default (`think: true` is HTTP 400 on
    models without thinking). Voice turns and titles never think.
    """
    return (os.getenv("TRANSCIBIO_OLLAMA_THINK") or "").strip().lower() in _TRUTHY


def resolve_ollama_num_ctx() -> int:
    raw = (os.getenv("TRANSCIBIO_OLLAMA_NUM_CTX") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_OLLAMA_NUM_CTX
    return max(value, _MIN_OLLAMA_NUM_CTX)


@dataclass(frozen=True)
class LocalLlmConfig:
    provider: str
    model_name: str
    # Reasoning for typed chat + transcript correction (Settings switch, else env default).
    think: bool = False


def normalize_backend_llm_provider(raw: str | None) -> str:
    return "ollama"


def resolve_local_llm_config(*, store: SQLiteStore, settings: AppSettings) -> LocalLlmConfig:
    provider = normalize_backend_llm_provider(settings.llm_provider)
    model_name = ""
    think = resolve_ollama_think()

    persisted = store.get_app_setting(_SETTINGS_KEY) or {}
    if isinstance(persisted, dict):
        chat = persisted.get("chat")
        if isinstance(chat, dict):
            provider = normalize_backend_llm_provider(str(chat.get("llm_provider") or provider))
            raw_model_name = chat.get("model_name")
            if isinstance(raw_model_name, str):
                model_name = raw_model_name.strip()
            raw_think = chat.get("think")
            if isinstance(raw_think, bool):
                think = raw_think

    return LocalLlmConfig(
        provider="ollama",
        model_name=model_name or os.getenv("TRANSCIBIO_OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL),
        think=think,
    )
