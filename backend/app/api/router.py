from fastapi import APIRouter

from backend.app.api.routers import (
    actions,
    chat,
    events,
    health,
    jobs,
    sessions,
    settings,
    tts,
    voice_commands,
    voice_turn,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(sessions.router)
api_router.include_router(chat.router)
api_router.include_router(voice_commands.router)
api_router.include_router(actions.router)
api_router.include_router(jobs.router)
api_router.include_router(settings.router)
api_router.include_router(tts.router)
api_router.include_router(events.router)
api_router.include_router(voice_turn.router)
