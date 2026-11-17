from __future__ import annotations

import os
import shutil
from urllib.error import URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


def _check_http(url: str, *, timeout_seconds: float = 0.4) -> dict[str, object]:
    try:
        request = UrlRequest(url, method="GET")
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - local health probe
            code = getattr(response, "status", 200)
        return {"reachable": True, "status_code": int(code)}
    except URLError as exc:
        return {"reachable": False, "error": str(exc.reason)}
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"reachable": False, "error": str(exc)}


def _provider_readiness() -> dict[str, object]:
    lmstudio_models_url = os.getenv(
        "TRANSCIBIO_LMSTUDIO_MODELS_URL", "http://127.0.0.1:1234/v1/models"
    )
    ollama_tags_url = os.getenv("TRANSCIBIO_OLLAMA_TAGS_URL", "http://127.0.0.1:11434/api/tags")
    piper_bin = os.getenv("TRANSCIBIO_PIPER_BIN") or shutil.which("piper") or ""
    piper_model = os.getenv("TRANSCIBIO_PIPER_MODEL") or ""
    return {
        "lmstudio": {
            "models_url": lmstudio_models_url,
            **_check_http(lmstudio_models_url),
        },
        "ollama": {
            "tags_url": ollama_tags_url,
            **_check_http(ollama_tags_url),
        },
        "piper": {
            "binary_found": bool(piper_bin),
            "binary_path": piper_bin,
            "model_configured": bool(piper_model),
            "model_path": piper_model,
        },
    }


@router.get("/healthz")
def healthz(request: Request) -> dict[str, object]:
    settings = getattr(request.app.state, "settings", None)
    runtime = getattr(request.app.state, "runtime", {})
    if settings is None:
        return {"status": "ok", "runtime_initialized": False}
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "environment": settings.environment,
        "runtime_initialized": bool(runtime),
        "profile": settings.processing_profile,
        "data_root": str(settings.data_root),
        "db_path": str(settings.db_path),
        "sessions_root": str(settings.sessions_root),
        "ffmpeg": runtime.get("ffmpeg", {}),
        "provider_readiness": _provider_readiness(),
    }
