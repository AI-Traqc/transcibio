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


@dataclass
class ModelDiscoveryService:
    _ollama_cache: _CacheEntry = field(default_factory=_CacheEntry)

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
