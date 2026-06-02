from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.app.api.deps import get_app_settings, get_job_runtime, get_runtime_info, get_store
from backend.app.config import AppSettings
from backend.app.services.audio_storage import (
    AudioConversionError,
    AudioProbeError,
    AudioStorageService,
    AudioValidationError,
)
from backend.app.services.job_runtime import JobRuntime
from backend.app.services.stt import FasterWhisperSttClient, SttError
from backend.app.store import SQLiteStore

router = APIRouter(tags=["voice-commands"])


class VoiceCommandResponse(BaseModel):
    voice_command_id: str
    session_id: str
    thread_id: str
    audio_asset_id: str
    send_mode: str
    transcribed_text: str
    edited_text: str
    detected_language: str
    stt_model: str
    warning: str = ""
    # True when STT produced no usable text (silence/noise or STT unavailable) and
    # `transcribed_text` is a human-facing placeholder, not a real utterance. The
    # hands-free loop uses this to skip non-speech instead of sending the placeholder
    # to the model; the manual review UI ignores it and shows the placeholder to edit.
    transcription_empty: bool = False
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    job_id: str | None = None


def _audio_service_from_runtime(
    *,
    settings: AppSettings,
    runtime_info: dict[str, object],
) -> AudioStorageService:
    ffmpeg_info = runtime_info.get("ffmpeg", {})
    ffmpeg_path = None
    ffprobe_path = None
    if isinstance(ffmpeg_info, dict):
        raw_ffmpeg = ffmpeg_info.get("ffmpeg_path")
        raw_ffprobe = ffmpeg_info.get("ffprobe_path")
        if isinstance(raw_ffmpeg, str) and raw_ffmpeg:
            ffmpeg_path = raw_ffmpeg
        if isinstance(raw_ffprobe, str) and raw_ffprobe:
            ffprobe_path = raw_ffprobe
    return AudioStorageService(settings, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path)


@router.post("/sessions/{session_id}/voice-commands", response_model=VoiceCommandResponse)
def create_voice_command(
    session_id: str,
    audio_file: UploadFile = File(...),
    send_mode: str = Form("review_then_send"),
    language_hint: str = Form("auto"),
    transcript_revision_id: str | None = Form(default=None),
    auto_send: bool | None = Form(default=None),
    store: SQLiteStore = Depends(get_store),
    settings: AppSettings = Depends(get_app_settings),
    runtime_info: dict[str, object] = Depends(get_runtime_info),
    job_runtime: JobRuntime = Depends(get_job_runtime),
) -> VoiceCommandResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    normalized_send_mode = send_mode.strip().lower()
    if auto_send is True:
        normalized_send_mode = "auto_send"
    if normalized_send_mode not in {"review_then_send", "auto_send"}:
        raise HTTPException(
            status_code=400, detail="send_mode must be review_then_send or auto_send"
        )

    service = _audio_service_from_runtime(settings=settings, runtime_info=runtime_info)
    filename = audio_file.filename or "command.webm"
    try:
        stored = service.save_recording_upload(
            session_id=session_id,
            filename=filename,
            content_type=audio_file.content_type,
            fileobj=audio_file.file,
            max_duration_ms=2 * 60 * 1000,
            normalize_sample_rate_hz=16000,
        )
    except AudioValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AudioProbeError, AudioConversionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        audio_file.file.close()

    audio_asset = store.create_audio_asset(
        session_id=session_id,
        kind="voice_command_audio",
        mime_type=stored.mime_type,
        file_path=stored.relative_path,
        duration_ms=stored.duration_ms,
        sample_rate_hz=stored.sample_rate_hz,
        channels=stored.channels,
    )

    warning = ""
    stt_model = ""
    detected_language = ""
    transcribed_text = ""
    try:
        stt_client = FasterWhisperSttClient()
        result = stt_client.transcribe_command(
            settings.data_root / stored.relative_path,
            language_hint=language_hint if language_hint in {"auto", "en", "de"} else "auto",
            preset=None,
        )
        transcribed_text = (result.text or "").strip()
        detected_language = result.detected_language or ""
        stt_model = result.model_name
    except SttError as exc:
        warning = str(exc)
        transcribed_text = ""
        detected_language = ""
        stt_model = "fallback"

    # No usable transcription (silence/noise, or STT unavailable): flag it and fill in a
    # human-facing placeholder for the manual review UI. The `warning` distinguishes an
    # STT failure from genuine silence.
    transcription_empty = not transcribed_text
    if transcription_empty:
        transcribed_text = (
            "Voice command transcription unavailable - please edit before sending."
            if warning
            else "Voice command transcription was empty - please edit before sending."
        )

    thread = store.get_or_create_chat_thread(session_id=session_id)

    user_message_id: str | None = None
    assistant_message_id: str | None = None
    job_id: str | None = None

    if normalized_send_mode == "auto_send":
        revision = None
        if transcript_revision_id:
            revision = store.get_transcript_revision(transcript_revision_id)
            if revision is None or revision.session_id != session_id:
                raise HTTPException(status_code=404, detail="Transcript revision not found")
        else:
            revision = store.get_latest_transcript_revision_for_session(session_id)
        if revision is None:
            raise HTTPException(
                status_code=400, detail="No transcript available for auto-send voice commands."
            )
        user_message = store.create_chat_message(
            thread_id=thread.id,
            session_id=session_id,
            transcript_revision_id=revision.id,
            role="user",
            content_markdown=transcribed_text,
            content_plain_text=transcribed_text,
            source_kind="voice_command",
            status="completed",
        )
        assistant_placeholder = store.create_chat_message(
            thread_id=thread.id,
            session_id=session_id,
            transcript_revision_id=revision.id,
            role="assistant",
            content_markdown="",
            content_plain_text="",
            source_kind="assistant_reply",
            status="queued",
            metadata={"pending": True, "trigger": "voice_command"},
        )
        job_id = job_runtime.enqueue_chat_reply_job(
            session_id=session_id,
            thread_id=thread.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_placeholder.id,
            transcript_revision_id=revision.id,
        )
        user_message_id = user_message.id
        assistant_message_id = assistant_placeholder.id

    voice_command = store.create_voice_command(
        session_id=session_id,
        thread_id=thread.id,
        audio_asset_id=audio_asset.id,
        transcribed_text=transcribed_text,
        edited_text="",
        send_mode=normalized_send_mode,
        detected_language=detected_language,
        stt_model=stt_model,
        sent_message_id=user_message_id,
    )

    return VoiceCommandResponse(
        voice_command_id=voice_command.id,
        session_id=session_id,
        thread_id=thread.id,
        audio_asset_id=audio_asset.id,
        send_mode=normalized_send_mode,
        transcribed_text=voice_command.transcribed_text,
        edited_text=voice_command.edited_text,
        detected_language=voice_command.detected_language,
        stt_model=voice_command.stt_model,
        warning=warning,
        transcription_empty=transcription_empty,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        job_id=job_id,
    )
