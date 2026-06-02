from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.router import api_router
from backend.app.config import AppSettings, get_settings, initialize_runtime
from backend.app.services.actions import ActionOrchestrator
from backend.app.services.chat_orchestrator import ChatOrchestrator
from backend.app.services.job_runtime import JobRuntime
from backend.app.services.model_discovery import ModelDiscoveryService
from backend.app.services.retrieval import TranscriptRetriever
from backend.app.services.transcription_orchestrator import build_default_transcription_orchestrator
from backend.app.services.tts import TtsOrchestrator
from backend.app.store import SQLiteStore


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = resolved_settings

    @app.on_event("startup")
    async def _startup() -> None:
        app.state.runtime = initialize_runtime(resolved_settings)
        app.state.store = SQLiteStore(resolved_settings.db_path)
        app.state.store.initialize()
        app.state.transcription_orchestrator = build_default_transcription_orchestrator(
            store=app.state.store,
            settings=resolved_settings,
        )
        app.state.transcript_retriever = TranscriptRetriever(app.state.store, resolved_settings)
        app.state.chat_orchestrator = ChatOrchestrator(
            store=app.state.store,
            settings=resolved_settings,
            retriever=app.state.transcript_retriever,
        )
        app.state.action_orchestrator = ActionOrchestrator(
            store=app.state.store,
            settings=resolved_settings,
        )
        app.state.tts_orchestrator = TtsOrchestrator(
            store=app.state.store,
            settings=resolved_settings,
        )
        app.state.model_discovery = ModelDiscoveryService()
        app.state.job_runtime = JobRuntime(
            app.state.store,
            transcription_orchestrator=app.state.transcription_orchestrator,
            chat_orchestrator=app.state.chat_orchestrator,
            settings=resolved_settings,
        )
        app.state.job_runtime.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        job_runtime = getattr(app.state, "job_runtime", None)
        if job_runtime is not None:
            job_runtime.stop()

    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
