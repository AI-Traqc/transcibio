from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from urllib.error import URLError
from urllib.request import Request, urlopen

_CACHE_TTL_SECONDS = 60

_KNOWN_STT_MODELS: tuple[str, ...] = (
    "tiny",
    "base",
    "small",
    "medium",
    "large-v2",
    "large-v3",
)


@dataclass(frozen=True)
class ProviderModels:
    provider: str
    current: str
    available: tuple[str, ...]
    reachable: bool
    error: str = ""


@dataclass
class _CacheEntry:
    models: tuple[str, ...] = ()
    fetched_at: float = 0.0


# Thinking support per Ollama model, for the Settings switch next to the chat model:
#   "optional": has the `thinking` capability and honors `think: false` (gemma4, qwen3, ...)
#   "always":   reasons even with `think: false` (gpt-oss), so the switch can't turn it off
#   "none":     no thinking capability (granite, ...)
ThinkingSupport = str
_ALWAYS_THINKING_FAMILIES = frozenset({"gptoss"})


def thinking_support_from_show(show: dict) -> ThinkingSupport:
    """Classify one `/api/show` response."""
    capabilities = show.get("capabilities") or []
    if "thinking" not in capabilities:
        return "none"
    family = str((show.get("details") or {}).get("family") or "").lower()
    return "always" if family in _ALWAYS_THINKING_FAMILIES else "optional"


@dataclass
class ModelDiscoveryService:
    _ollama_cache: _CacheEntry = field(default_factory=_CacheEntry)
    # A model's capabilities don't change, so each is looked up once.
    _thinking_cache: dict[str, ThinkingSupport] = field(default_factory=dict)

    def get_llm_thinking_support(self, models: tuple[str, ...]) -> dict[str, ThinkingSupport]:
        """`{model: "optional" | "always" | "none"}` via Ollama's `/api/show`; models whose
        lookup fails are left out (the dialog then leaves the switch enabled)."""
        tags_url = os.getenv("TRANSCIBIO_OLLAMA_TAGS_URL", "http://127.0.0.1:11434/api/tags")
        show_url = tags_url.rsplit("/api/", 1)[0] + "/api/show"
        for name in models:
            if name in self._thinking_cache:
                continue
            try:
                req = Request(
                    show_url,
                    data=json.dumps({"model": name}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(req, timeout=2) as resp:  # noqa: S310
                    self._thinking_cache[name] = thinking_support_from_show(json.loads(resp.read()))
            except (URLError, OSError, json.JSONDecodeError):
                continue
        return {name: self._thinking_cache[name] for name in models if name in self._thinking_cache}

    def get_stt_models(self, *, current_model: str) -> ProviderModels:
        return ProviderModels(
            provider="faster-whisper",
            current=current_model,
            available=_KNOWN_STT_MODELS,
            reachable=True,
        )

    def get_llm_models(self, *, current_model: str) -> ProviderModels:
        now = time.monotonic()
        if self._ollama_cache.models and now - self._ollama_cache.fetched_at < _CACHE_TTL_SECONDS:
            return ProviderModels(
                provider="ollama",
                current=current_model,
                available=self._ollama_cache.models,
                reachable=True,
            )

        tags_url = os.getenv("TRANSCIBIO_OLLAMA_TAGS_URL", "http://127.0.0.1:11434/api/tags")
        try:
            req = Request(tags_url, method="GET")
            with urlopen(req, timeout=2) as resp:  # noqa: S310
                data = json.loads(resp.read())
            names = tuple(
                m["name"] for m in data.get("models", []) if isinstance(m, dict) and "name" in m
            )
            self._ollama_cache = _CacheEntry(models=names, fetched_at=now)
            return ProviderModels(
                provider="ollama",
                current=current_model,
                available=names,
                reachable=True,
            )
        except (URLError, OSError, json.JSONDecodeError, KeyError) as exc:
            if self._ollama_cache.models:
                return ProviderModels(
                    provider="ollama",
                    current=current_model,
                    available=self._ollama_cache.models,
                    reachable=False,
                    error=str(exc),
                )
            return ProviderModels(
                provider="ollama",
                current=current_model,
                available=(),
                reachable=False,
                error=str(exc),
            )

    def get_diarization_info(self, *, enabled: bool) -> ProviderModels:
        return ProviderModels(
            provider="pyannote",
            current="pyannote/speaker-diarization-3.1",
            available=("pyannote/speaker-diarization-3.1",),
            reachable=True,
        )
