from __future__ import annotations

from fastapi import HTTPException, Request

from backend.app.config import AppSettings
from backend.app.services.actions import ActionOrchestrator
from backend.app.services.chat_orchestrator import ChatOrchestrator
from backend.app.services.job_runtime import JobRuntime
from backend.app.services.model_discovery import ModelDiscoveryService
from backend.app.services.tts import TtsOrchestrator
from backend.app.store import SQLiteStore


def get_store(request: Request) -> SQLiteStore:
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(status_code=500, detail="Store not initialized")
    return store


def get_app_settings(request: Request) -> AppSettings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise HTTPException(status_code=500, detail="Settings not initialized")
    return settings


def get_job_runtime(request: Request) -> JobRuntime:
    runtime = getattr(request.app.state, "job_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=500, detail="Job runtime not initialized")
    return runtime


def get_chat_orchestrator(request: Request) -> ChatOrchestrator:
    orchestrator = getattr(request.app.state, "chat_orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status_code=500, detail="Chat orchestrator not initialized")
    return orchestrator


def get_action_orchestrator(request: Request) -> ActionOrchestrator:
    orchestrator = getattr(request.app.state, "action_orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status_code=500, detail="Action orchestrator not initialized")
    return orchestrator


def get_tts_orchestrator(request: Request) -> TtsOrchestrator:
    orchestrator = getattr(request.app.state, "tts_orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status_code=500, detail="TTS orchestrator not initialized")
    return orchestrator


def get_runtime_info(request: Request) -> dict[str, object]:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=500, detail="Runtime not initialized")
    return runtime


def get_model_discovery(request: Request) -> ModelDiscoveryService:
    service = getattr(request.app.state, "model_discovery", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Model discovery not initialized")
    return service
