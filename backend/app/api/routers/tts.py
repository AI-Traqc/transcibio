from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.api.deps import get_tts_orchestrator
from backend.app.services.tts import TtsMessageStatus, TtsOrchestrator

router = APIRouter(tags=["tts"])


class GenerateTtsRequest(BaseModel):
    message_id: str = Field(min_length=1)
    voice: str | None = None
    speed: float | None = Field(default=None, ge=0.25, le=3.0)
    force_regenerate: bool = False


class TtsStatusResponse(BaseModel):
    message_id: str
    status: str
    audio_asset_id: str | None = None
    mime_type: str | None = None
    duration_ms: int | None = None
    error_message: str = ""
    download_url: str | None = None
    model_name: str = ""


def _to_response(status: TtsMessageStatus) -> TtsStatusResponse:
    return TtsStatusResponse(
        message_id=status.message_id,
        status=status.status,
        audio_asset_id=status.audio_asset_id,
        mime_type=status.mime_type,
        duration_ms=status.duration_ms,
        error_message=status.error_message,
        download_url=status.download_url,
        model_name=status.model_name,
    )


@router.post("/sessions/{session_id}/tts", response_model=TtsStatusResponse)
def generate_session_message_tts(
    session_id: str,
    payload: GenerateTtsRequest,
    orchestrator: TtsOrchestrator = Depends(get_tts_orchestrator),
) -> TtsStatusResponse:
    try:
        status = orchestrator.generate_for_message(
            session_id=session_id,
            message_id=payload.message_id,
            voice=payload.voice,
            speed=payload.speed,
            force_regenerate=payload.force_regenerate,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Chat message not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _to_response(status)


@router.get("/sessions/{session_id}/tts/{message_id}", response_model=TtsStatusResponse)
def get_session_message_tts_status(
    session_id: str,
    message_id: str,
    orchestrator: TtsOrchestrator = Depends(get_tts_orchestrator),
) -> TtsStatusResponse:
    try:
        status = orchestrator.get_message_status(session_id=session_id, message_id=message_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Chat message not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(status)


@router.get("/sessions/{session_id}/tts/{message_id}/audio")
def get_session_message_tts_audio(
    session_id: str,
    message_id: str,
    orchestrator: TtsOrchestrator = Depends(get_tts_orchestrator),
) -> FileResponse:
    try:
        path = orchestrator.get_audio_path(session_id=session_id, message_id=message_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="TTS audio not found") from exc
    return FileResponse(path, media_type="audio/wav", filename=path.name)
