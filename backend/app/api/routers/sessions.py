from __future__ import annotations

import json
import shutil

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.api.deps import get_app_settings, get_job_runtime, get_runtime_info, get_store
from backend.app.config import AppSettings
from backend.app.services.audio_storage import (
    AudioConversionError,
    AudioProbeError,
    AudioStorageService,
    AudioValidationError,
)
from backend.app.services.job_runtime import JobRuntime
from backend.app.services.retrieval import TranscriptRetriever
from backend.app.services.transcript_correction import (
    TranscriptCorrectionApplyResult,
    TranscriptCorrectionProposalResult,
    TranscriptCorrectionService,
)
from backend.app.store import SQLiteStore

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_kind: str = Field(default="upload", pattern="^(upload|recording)$")
    source_name: str = Field(default="")
    source_language_hint: str = Field(default="auto")
    command_language_hint: str = Field(default="auto")


class UpdateSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class SessionResponse(BaseModel):
    id: str
    created_at_utc: str
    updated_at_utc: str
    title: str
    source_kind: str
    source_name: str
    source_language_hint: str
    command_language_hint: str
    status: str
    last_error: str
    active_transcript_revision_id: str | None


class AudioUploadResponse(BaseModel):
    audio_asset_id: str
    session_id: str
    kind: str
    file_name: str
    file_path: str
    mime_type: str
    duration_ms: int
    sample_rate_hz: int | None
    channels: int | None


class CreateTranscriptionJobRequest(BaseModel):
    audio_asset_id: str
    language_hint: str = Field(default="auto", pattern="^(auto|en|de)$")
    stt_preset: str = Field(default="balanced", pattern="^(fast|balanced|quality)$")
    diarization_enabled: bool = True


class CreateTranscriptionJobResponse(BaseModel):
    job_id: str
    status: str


class TranscriptRevisionSummaryResponse(BaseModel):
    id: str
    revision_number: int
    created_at_utc: str
    created_by: str
    source: str
    parent_revision_id: str | None
    language_detected: str
    diarization_used: bool
    stt_model: str
    warnings: list[str] = Field(default_factory=list)


class TranscriptSpeakerResponse(BaseModel):
    id: str
    speaker_key: str
    display_name: str
    sort_order: int


class TranscriptSegmentResponse(BaseModel):
    id: str
    segment_index: int
    speaker_id: str | None
    speaker_key: str | None
    speaker_display_name: str | None
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None
    word_count: int


class TranscriptResponse(BaseModel):
    session_id: str
    revision: TranscriptRevisionSummaryResponse
    speakers: list[TranscriptSpeakerResponse]
    segments: list[TranscriptSegmentResponse]


class PatchTranscriptSegmentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class PatchTranscriptSpeakerRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)


class CreateTranscriptCorrectionProposalRequest(BaseModel):
    revision_id: str | None = None
    scope_type: str = Field(
        default="full_transcript", pattern="^(full_transcript|segment_ids|time_range_ms)$"
    )
    segment_ids: list[str] = Field(default_factory=list)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    strategy: str = Field(default="auto", pattern="^(auto|llm|rules)$")


class TranscriptCorrectionSegmentChangeResponse(BaseModel):
    segment_id: str
    segment_index: int
    start_ms: int
    end_ms: int
    before_text: str
    after_text: str


class TranscriptCorrectionProposalResponse(BaseModel):
    proposal_id: str
    session_id: str
    base_revision_id: str
    strategy_used: str
    model_name: str
    changed_segment_count: int
    warnings: list[str] = Field(default_factory=list)
    diff_preview: dict = Field(default_factory=dict)
    segment_changes: list[TranscriptCorrectionSegmentChangeResponse] = Field(default_factory=list)


class ApplyTranscriptCorrectionResponse(BaseModel):
    proposal_id: str
    status: str
    applied_revision_id: str
    revision_number: int
    changed_segment_count: int
    transcript: TranscriptResponse


def _to_response(record: object) -> SessionResponse:
    return SessionResponse.model_validate(record, from_attributes=True)


def _to_transcript_revision_summary(record: object) -> TranscriptRevisionSummaryResponse:
    parsed = TranscriptRevisionSummaryResponse.model_validate(record, from_attributes=True)
    warnings_json = getattr(record, "warnings_json", "[]")
    try:
        warnings = json.loads(warnings_json)
    except Exception:
        warnings = []
    return parsed.model_copy(update={"warnings": warnings if isinstance(warnings, list) else []})


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


def _transcript_correction_service(
    *,
    store: SQLiteStore,
    settings: AppSettings,
) -> TranscriptCorrectionService:
    return TranscriptCorrectionService(
        store=store,
        settings=settings,
        retriever=TranscriptRetriever(store, settings),
    )


def _persist_audio_response(
    *,
    store: SQLiteStore,
    session_id: str,
    stored,
    kind: str = "meeting_audio",
) -> AudioUploadResponse:
    asset = store.create_audio_asset(
        session_id=session_id,
        kind=kind,
        mime_type=stored.mime_type,
        file_path=stored.relative_path,
        duration_ms=stored.duration_ms,
        sample_rate_hz=stored.sample_rate_hz,
        channels=stored.channels,
    )
    return AudioUploadResponse(
        audio_asset_id=asset.id,
        session_id=asset.session_id,
        kind=asset.kind,
        file_name=stored.original_filename,
        file_path=asset.file_path,
        mime_type=asset.mime_type,
        duration_ms=asset.duration_ms,
        sample_rate_hz=asset.sample_rate_hz,
        channels=asset.channels,
    )


def _build_transcript_response(
    *,
    store: SQLiteStore,
    session_id: str,
    revision,
) -> TranscriptResponse:
    speakers = store.list_transcript_speakers(revision.id)
    speaker_map = {speaker.id: speaker for speaker in speakers}
    segments = store.list_transcript_segments(revision.id)
    return TranscriptResponse(
        session_id=session_id,
        revision=_to_transcript_revision_summary(revision),
        speakers=[
            TranscriptSpeakerResponse.model_validate(item, from_attributes=True)
            for item in speakers
        ],
        segments=[
            TranscriptSegmentResponse(
                id=item.id,
                segment_index=item.segment_index,
                speaker_id=item.speaker_id,
                speaker_key=speaker_map[item.speaker_id].speaker_key
                if item.speaker_id in speaker_map
                else None,
                speaker_display_name=(
                    speaker_map[item.speaker_id].display_name
                    if item.speaker_id in speaker_map
                    else None
                ),
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                text=item.text,
                confidence=item.confidence,
                word_count=item.word_count,
            )
            for item in segments
        ],
    )


def _to_correction_proposal_response(
    result: TranscriptCorrectionProposalResult,
) -> TranscriptCorrectionProposalResponse:
    return TranscriptCorrectionProposalResponse(
        proposal_id=result.proposal_id,
        session_id=result.session_id,
        base_revision_id=result.base_revision_id,
        strategy_used=result.strategy_used,
        model_name=result.model_name,
        changed_segment_count=result.changed_segment_count,
        warnings=result.warnings,
        diff_preview=result.diff_preview,
        segment_changes=[
            TranscriptCorrectionSegmentChangeResponse(
                segment_id=item.segment_id,
                segment_index=item.segment_index,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                before_text=item.before_text,
                after_text=item.after_text,
            )
            for item in result.segment_changes
        ],
    )


@router.post("", response_model=SessionResponse)
def create_session(
    payload: CreateSessionRequest,
    store: SQLiteStore = Depends(get_store),
) -> SessionResponse:
    record = store.create_session(
        title=payload.title,
        source_kind=payload.source_kind,
        source_name=payload.source_name,
        source_language_hint=payload.source_language_hint,
        command_language_hint=payload.command_language_hint,
    )
    return _to_response(record)


@router.get("", response_model=list[SessionResponse])
def list_sessions(
    q: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    store: SQLiteStore = Depends(get_store),
) -> list[SessionResponse]:
    return [_to_response(item) for item in store.list_sessions(query=q, limit=limit)]


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    store: SQLiteStore = Depends(get_store),
) -> SessionResponse:
    record = store.get_session(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_response(record)


@router.patch("/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: str,
    payload: UpdateSessionRequest,
    store: SQLiteStore = Depends(get_store),
) -> SessionResponse:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        record = store.update_session_title(session_id, payload.title)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return _to_response(record)


class DeleteAllSessionsResponse(BaseModel):
    deleted_count: int


@router.delete("", response_model=DeleteAllSessionsResponse)
def delete_all_sessions(
    store: SQLiteStore = Depends(get_store),
    job_runtime: JobRuntime = Depends(get_job_runtime),
    settings: AppSettings = Depends(get_app_settings),
) -> DeleteAllSessionsResponse:
    deleted = 0
    while True:
        batch = store.list_sessions(query="", limit=200)
        if not batch:
            break
        for session in batch:
            for active in store.list_active_jobs_for_session(session.id):
                job_runtime.mark_canceled(active.id, reason="session_deleted")
            if store.delete_session_cascade(session.id):
                deleted += 1
                session_dir = settings.sessions_root / session.id
                if session_dir.exists():
                    shutil.rmtree(session_dir, ignore_errors=True)
        if len(batch) < 200:
            break
    return DeleteAllSessionsResponse(deleted_count=deleted)


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    store: SQLiteStore = Depends(get_store),
    job_runtime: JobRuntime = Depends(get_job_runtime),
    settings: AppSettings = Depends(get_app_settings),
) -> Response:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    for active in store.list_active_jobs_for_session(session_id):
        job_runtime.mark_canceled(active.id, reason="session_deleted")

    deleted = store.delete_session_cascade(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    session_dir = settings.sessions_root / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)

    return Response(status_code=204)


@router.post("/{session_id}/audio/upload", response_model=AudioUploadResponse)
def upload_session_audio(
    session_id: str,
    audio_file: UploadFile = File(...),
    store: SQLiteStore = Depends(get_store),
    settings: AppSettings = Depends(get_app_settings),
    runtime_info: dict[str, object] = Depends(get_runtime_info),
) -> AudioUploadResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not audio_file.filename:
        raise HTTPException(status_code=400, detail="Missing file name")
    service = _audio_service_from_runtime(settings=settings, runtime_info=runtime_info)

    try:
        stored = service.save_meeting_upload(
            session_id=session_id,
            filename=audio_file.filename,
            content_type=audio_file.content_type,
            fileobj=audio_file.file,
        )
    except AudioValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AudioProbeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        audio_file.file.close()

    return _persist_audio_response(store=store, session_id=session_id, stored=stored)


@router.get("/{session_id}/audio", response_model=AudioUploadResponse | None)
def get_session_audio(
    session_id: str,
    store: SQLiteStore = Depends(get_store),
) -> AudioUploadResponse | None:
    asset = store.get_audio_asset_for_session(session_id)
    if asset is None:
        return None
    return AudioUploadResponse(
        audio_asset_id=asset.id,
        session_id=asset.session_id,
        kind=asset.kind,
        file_name=asset.file_path.rsplit("/", 1)[-1],
        file_path=asset.file_path,
        mime_type=asset.mime_type,
        duration_ms=asset.duration_ms,
        sample_rate_hz=asset.sample_rate_hz,
        channels=asset.channels,
    )


@router.get("/{session_id}/audio/{audio_asset_id}/stream")
def stream_session_audio(
    session_id: str,
    audio_asset_id: str,
    store: SQLiteStore = Depends(get_store),
    settings: AppSettings = Depends(get_app_settings),
) -> FileResponse:
    asset = store.get_audio_asset(audio_asset_id)
    if asset is None or asset.session_id != session_id:
        raise HTTPException(status_code=404, detail="Audio asset not found")
    path = settings.data_root / asset.file_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path, media_type=asset.mime_type, filename=path.name)


@router.post("/{session_id}/transcription-jobs", response_model=CreateTranscriptionJobResponse)
def create_transcription_job(
    session_id: str,
    payload: CreateTranscriptionJobRequest,
    store: SQLiteStore = Depends(get_store),
    job_runtime: JobRuntime = Depends(get_job_runtime),
) -> CreateTranscriptionJobResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    audio_asset = store.get_audio_asset(payload.audio_asset_id)
    if audio_asset is None or audio_asset.session_id != session_id:
        raise HTTPException(status_code=404, detail="Audio asset not found")

    if audio_asset.kind != "meeting_audio":
        raise HTTPException(
            status_code=400, detail="Only meeting audio can be transcribed into a transcript."
        )

    store.update_session_status(session_id, status="processing", last_error="")
    job_id = job_runtime.enqueue_transcription_job(
        session_id=session_id,
        audio_asset_id=payload.audio_asset_id,
        language_hint=payload.language_hint,
        stt_preset=payload.stt_preset,
        diarization_enabled=payload.diarization_enabled,
    )
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Failed to create transcription job")
    return CreateTranscriptionJobResponse(job_id=job_id, status=job.status)


@router.get("/{session_id}/transcript", response_model=TranscriptResponse)
def get_session_transcript(
    session_id: str,
    revision_id: str | None = Query(default=None),
    store: SQLiteStore = Depends(get_store),
) -> TranscriptResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if revision_id:
        revision = store.get_transcript_revision(revision_id)
        if revision is None or revision.session_id != session_id:
            raise HTTPException(status_code=404, detail="Transcript revision not found")
    else:
        revision = store.get_latest_transcript_revision_for_session(session_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="No transcript found for this session")

    return _build_transcript_response(store=store, session_id=session_id, revision=revision)


@router.get(
    "/{session_id}/transcript/revisions", response_model=list[TranscriptRevisionSummaryResponse]
)
def list_session_transcript_revisions(
    session_id: str,
    store: SQLiteStore = Depends(get_store),
) -> list[TranscriptRevisionSummaryResponse]:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return [
        _to_transcript_revision_summary(item)
        for item in store.list_transcript_revisions(session_id)
    ]


@router.patch(
    "/{session_id}/transcript/segments/{segment_id}",
    response_model=TranscriptResponse,
)
def patch_transcript_segment(
    session_id: str,
    segment_id: str,
    payload: PatchTranscriptSegmentRequest,
    store: SQLiteStore = Depends(get_store),
) -> TranscriptResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        result = store.edit_transcript_segment_text(
            session_id=session_id,
            segment_id=segment_id,
            new_text=payload.text,
            actor="user",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Transcript segment not found") from exc
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if "latest transcript revision" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc

    return _build_transcript_response(store=store, session_id=session_id, revision=result.revision)


@router.patch(
    "/{session_id}/transcript/speakers/{speaker_id}",
    response_model=TranscriptResponse,
)
def patch_transcript_speaker(
    session_id: str,
    speaker_id: str,
    payload: PatchTranscriptSpeakerRequest,
    store: SQLiteStore = Depends(get_store),
) -> TranscriptResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        result = store.rename_transcript_speaker(
            session_id=session_id,
            speaker_id=speaker_id,
            display_name=payload.display_name,
            actor="user",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Transcript speaker not found") from exc
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if "latest transcript revision" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc

    return _build_transcript_response(store=store, session_id=session_id, revision=result.revision)


@router.post(
    "/{session_id}/transcript/correction-proposals",
    response_model=TranscriptCorrectionProposalResponse,
)
def create_transcript_correction_proposal(
    session_id: str,
    payload: CreateTranscriptCorrectionProposalRequest,
    store: SQLiteStore = Depends(get_store),
    settings: AppSettings = Depends(get_app_settings),
) -> TranscriptCorrectionProposalResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    service = _transcript_correction_service(store=store, settings=settings)
    try:
        result = service.generate_proposal(
            session_id=session_id,
            revision_id=payload.revision_id,
            scope_type=payload.scope_type,  # validated by pydantic
            segment_ids=payload.segment_ids,
            start_ms=payload.start_ms,
            end_ms=payload.end_ms,
            strategy=payload.strategy,  # validated by pydantic
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Transcript revision not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_correction_proposal_response(result)


@router.get(
    "/{session_id}/transcript/correction-proposals/{proposal_id}",
    response_model=TranscriptCorrectionProposalResponse,
)
def get_transcript_correction_proposal(
    session_id: str,
    proposal_id: str,
    store: SQLiteStore = Depends(get_store),
    settings: AppSettings = Depends(get_app_settings),
) -> TranscriptCorrectionProposalResponse:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    service = _transcript_correction_service(store=store, settings=settings)
    try:
        result = service.get_proposal(session_id=session_id, proposal_id=proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Correction proposal not found") from exc
    return _to_correction_proposal_response(result)


@router.post(
    "/{session_id}/transcript/correction-proposals/{proposal_id}/apply",
    response_model=ApplyTranscriptCorrectionResponse,
)
def apply_transcript_correction_proposal(
    session_id: str,
    proposal_id: str,
    store: SQLiteStore = Depends(get_store),
    settings: AppSettings = Depends(get_app_settings),
) -> ApplyTranscriptCorrectionResponse:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    service = _transcript_correction_service(store=store, settings=settings)
    try:
        result: TranscriptCorrectionApplyResult = service.apply_proposal(
            session_id=session_id,
            proposal_id=proposal_id,
            actor="user",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Correction proposal not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        detail = str(exc)
        if "Regenerate and try again" in detail:
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=500, detail=detail) from exc

    revision = store.get_transcript_revision(result.applied_revision_id)
    if revision is None:
        raise HTTPException(status_code=500, detail="Applied transcript revision not found")
    transcript = _build_transcript_response(store=store, session_id=session_id, revision=revision)
    return ApplyTranscriptCorrectionResponse(
        proposal_id=result.proposal_id,
        status=result.status,
        applied_revision_id=result.applied_revision_id,
        revision_number=result.revision_number,
        changed_segment_count=result.changed_segment_count,
        transcript=transcript,
    )


@router.post("/{session_id}/audio/recording", response_model=AudioUploadResponse)
def upload_session_recording(
    session_id: str,
    audio_file: UploadFile = File(...),
    store: SQLiteStore = Depends(get_store),
    settings: AppSettings = Depends(get_app_settings),
    runtime_info: dict[str, object] = Depends(get_runtime_info),
) -> AudioUploadResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    service = _audio_service_from_runtime(settings=settings, runtime_info=runtime_info)
    filename = audio_file.filename or "recording.webm"

    try:
        stored = service.save_recording_upload(
            session_id=session_id,
            filename=filename,
            content_type=audio_file.content_type,
            fileobj=audio_file.file,
            max_duration_ms=15 * 60 * 1000,
            normalize_sample_rate_hz=16000,
        )
    except AudioValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AudioProbeError, AudioConversionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        audio_file.file.close()

    return _persist_audio_response(store=store, session_id=session_id, stored=stored)
