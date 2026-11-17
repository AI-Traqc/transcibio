from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.deps import get_job_runtime, get_store
from backend.app.services.job_runtime import JobRuntime
from backend.app.store import SQLiteStore

router = APIRouter(tags=["chat"])


class ChatCitationResponse(BaseModel):
    id: str
    citation_index: int
    segment_id: str
    start_ms: int
    end_ms: int
    quote_excerpt: str


class ChatActionProposalResponse(BaseModel):
    id: str
    action_type: str
    title: str
    status: str
    requires_confirmation: bool
    preview_markdown: str
    payload: dict = Field(default_factory=dict)
    created_at_utc: str
    updated_at_utc: str
    executed_at_utc: str | None = None
    error_message: str = ""
    executions: list[dict] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    id: str
    thread_id: str
    session_id: str
    transcript_revision_id: str | None = None
    role: str
    content_markdown: str
    content_plain_text: str
    source_kind: str
    status: str
    model_name: str
    created_at_utc: str
    metadata: dict = Field(default_factory=dict)
    citations: list[ChatCitationResponse] = Field(default_factory=list)
    action_proposals: list[ChatActionProposalResponse] = Field(default_factory=list)


class ChatThreadResponse(BaseModel):
    id: str
    session_id: str
    title: str
    created_at_utc: str
    updated_at_utc: str


class SessionChatResponse(BaseModel):
    session_id: str
    thread: ChatThreadResponse | None = None
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class CreateChatMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    source_kind: str = Field(default="typed", pattern="^(typed|voice_command)$")
    transcript_revision_id: str | None = None


class CreateChatMessageResponse(BaseModel):
    thread_id: str
    user_message_id: str
    assistant_message_id: str
    job_id: str
    status: str


def _parse_json_dict(raw_json: str) -> dict:
    try:
        parsed = json.loads(raw_json)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_action_response(store: SQLiteStore, record) -> ChatActionProposalResponse:
    executions = store.list_action_executions(record.id)
    artifacts = store.list_export_artifacts_for_action(record.id)
    return ChatActionProposalResponse(
        id=record.id,
        action_type=record.action_type,
        title=record.title,
        status=record.status,
        requires_confirmation=record.requires_confirmation,
        preview_markdown=record.preview_markdown,
        payload=_parse_json_dict(record.payload_json),
        created_at_utc=record.created_at_utc,
        updated_at_utc=record.updated_at_utc,
        executed_at_utc=record.executed_at_utc,
        error_message=record.error_message,
        executions=[
            {
                "id": item.id,
                "action_proposal_id": item.action_proposal_id,
                "created_at_utc": item.created_at_utc,
                "executor_kind": item.executor_kind,
                "status": item.status,
                "result": _parse_json_dict(item.result_json),
            }
            for item in executions
        ],
        artifacts=[
            {
                "id": item.id,
                "session_id": item.session_id,
                "action_proposal_id": item.action_proposal_id,
                "file_path": item.file_path,
                "file_name": item.file_name,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "created_at_utc": item.created_at_utc,
                "kind": item.kind,
            }
            for item in artifacts
        ],
    )


def _to_message_response(store: SQLiteStore, record) -> ChatMessageResponse:
    citations = store.list_message_citations(record.id)
    actions = store.list_action_proposals_for_message(record.id)
    return ChatMessageResponse(
        id=record.id,
        thread_id=record.thread_id,
        session_id=record.session_id,
        transcript_revision_id=record.transcript_revision_id,
        role=record.role,
        content_markdown=record.content_markdown,
        content_plain_text=record.content_plain_text,
        source_kind=record.source_kind,
        status=record.status,
        model_name=record.model_name,
        created_at_utc=record.created_at_utc,
        metadata=_parse_json_dict(record.metadata_json),
        citations=[
            ChatCitationResponse(
                id=item.id,
                citation_index=item.citation_index,
                segment_id=item.segment_id,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                quote_excerpt=item.quote_excerpt,
            )
            for item in citations
        ],
        action_proposals=[_to_action_response(store, item) for item in actions],
    )


@router.get("/sessions/{session_id}/chat", response_model=SessionChatResponse)
def get_session_chat(
    session_id: str,
    store: SQLiteStore = Depends(get_store),
) -> SessionChatResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    thread = store.get_chat_thread_for_session(session_id)
    if thread is None:
        return SessionChatResponse(session_id=session_id, thread=None, messages=[])

    messages = store.list_chat_messages(thread.id)
    return SessionChatResponse(
        session_id=session_id,
        thread=ChatThreadResponse.model_validate(thread, from_attributes=True),
        messages=[_to_message_response(store, item) for item in messages],
    )


@router.post("/sessions/{session_id}/chat/messages", response_model=CreateChatMessageResponse)
def create_chat_message(
    session_id: str,
    payload: CreateChatMessageRequest,
    store: SQLiteStore = Depends(get_store),
    job_runtime: JobRuntime = Depends(get_job_runtime),
) -> CreateChatMessageResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Transcript is optional: with one, answers are grounded in it; without one,
    # the model answers as a general assistant.
    transcript_revision = None
    if payload.transcript_revision_id:
        transcript_revision = store.get_transcript_revision(payload.transcript_revision_id)
        if transcript_revision is None or transcript_revision.session_id != session_id:
            raise HTTPException(status_code=404, detail="Transcript revision not found")
    else:
        transcript_revision = store.get_latest_transcript_revision_for_session(session_id)

    revision_id = transcript_revision.id if transcript_revision else None
    thread = store.get_or_create_chat_thread(session_id=session_id)
    user_message = store.create_chat_message(
        thread_id=thread.id,
        session_id=session_id,
        transcript_revision_id=revision_id,
        role="user",
        content_markdown=payload.text.strip(),
        content_plain_text=payload.text.strip(),
        source_kind=payload.source_kind,
        status="completed",
    )
    assistant_placeholder = store.create_chat_message(
        thread_id=thread.id,
        session_id=session_id,
        transcript_revision_id=revision_id,
        role="assistant",
        content_markdown="",
        content_plain_text="",
        source_kind="assistant_reply",
        status="queued",
        metadata={"pending": True},
    )

    job_id = job_runtime.enqueue_chat_reply_job(
        session_id=session_id,
        thread_id=thread.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_placeholder.id,
        transcript_revision_id=revision_id,
    )
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Failed to create chat reply job")

    return CreateChatMessageResponse(
        thread_id=thread.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_placeholder.id,
        job_id=job_id,
        status=job.status,
    )


@router.get("/sessions/{session_id}/chat/messages/{message_id}", response_model=ChatMessageResponse)
def get_session_chat_message(
    session_id: str,
    message_id: str,
    store: SQLiteStore = Depends(get_store),
) -> ChatMessageResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    message = store.get_chat_message(message_id)
    if message is None or message.session_id != session_id:
        raise HTTPException(status_code=404, detail="Chat message not found")
    return _to_message_response(store, message)
