from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.api.deps import get_action_orchestrator, get_app_settings, get_store
from backend.app.config import AppSettings
from backend.app.services.actions import ActionOrchestrator
from backend.app.store import SQLiteStore

router = APIRouter(tags=["actions"])


class ExportArtifactResponse(BaseModel):
    id: str
    session_id: str
    action_proposal_id: str | None = None
    file_path: str
    file_name: str
    mime_type: str
    size_bytes: int
    created_at_utc: str
    kind: str


class ActionExecutionResponse(BaseModel):
    id: str
    action_proposal_id: str
    created_at_utc: str
    executor_kind: str
    status: str
    result: dict = Field(default_factory=dict)


class ActionProposalResponse(BaseModel):
    id: str
    session_id: str
    thread_id: str
    message_id: str
    action_type: str
    title: str
    status: str
    requires_confirmation: bool
    payload: dict = Field(default_factory=dict)
    preview_markdown: str
    created_at_utc: str
    updated_at_utc: str
    executed_at_utc: str | None = None
    error_message: str = ""
    executions: list[ActionExecutionResponse] = Field(default_factory=list)
    artifacts: list[ExportArtifactResponse] = Field(default_factory=list)


class ActionMutationResponse(BaseModel):
    action: ActionProposalResponse


def _parse_json_dict(raw_json: str) -> dict:
    try:
        parsed = json.loads(raw_json)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_action_response(store: SQLiteStore, record) -> ActionProposalResponse:
    executions = store.list_action_executions(record.id)
    artifacts = store.list_export_artifacts_for_action(record.id)
    return ActionProposalResponse(
        id=record.id,
        session_id=record.session_id,
        thread_id=record.thread_id,
        message_id=record.message_id,
        action_type=record.action_type,
        title=record.title,
        status=record.status,
        requires_confirmation=record.requires_confirmation,
        payload=_parse_json_dict(record.payload_json),
        preview_markdown=record.preview_markdown,
        created_at_utc=record.created_at_utc,
        updated_at_utc=record.updated_at_utc,
        executed_at_utc=record.executed_at_utc,
        error_message=record.error_message,
        executions=[
            ActionExecutionResponse(
                id=item.id,
                action_proposal_id=item.action_proposal_id,
                created_at_utc=item.created_at_utc,
                executor_kind=item.executor_kind,
                status=item.status,
                result=_parse_json_dict(item.result_json),
            )
            for item in executions
        ],
        artifacts=[
            ExportArtifactResponse.model_validate(item, from_attributes=True) for item in artifacts
        ],
    )


@router.get("/sessions/{session_id}/actions", response_model=list[ActionProposalResponse])
def list_actions(
    session_id: str,
    status: str | None = Query(default=None),
    store: SQLiteStore = Depends(get_store),
) -> list[ActionProposalResponse]:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return [
        _to_action_response(store, item)
        for item in store.list_action_proposals(session_id=session_id, status=status)
    ]


@router.post(
    "/sessions/{session_id}/actions/{action_id}/confirm", response_model=ActionMutationResponse
)
def confirm_action(
    session_id: str,
    action_id: str,
    store: SQLiteStore = Depends(get_store),
    action_orchestrator: ActionOrchestrator = Depends(get_action_orchestrator),
) -> ActionMutationResponse:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        action_orchestrator.confirm_action(session_id=session_id, action_id=action_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Action proposal not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    refreshed = store.get_action_proposal(action_id)
    if refreshed is None:
        raise HTTPException(
            status_code=500, detail="Action proposal disappeared after confirmation"
        )
    return ActionMutationResponse(action=_to_action_response(store, refreshed))


@router.post(
    "/sessions/{session_id}/actions/{action_id}/cancel", response_model=ActionMutationResponse
)
def cancel_action(
    session_id: str,
    action_id: str,
    store: SQLiteStore = Depends(get_store),
    action_orchestrator: ActionOrchestrator = Depends(get_action_orchestrator),
) -> ActionMutationResponse:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        action_orchestrator.cancel_action(session_id=session_id, action_id=action_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Action proposal not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    refreshed = store.get_action_proposal(action_id)
    if refreshed is None:
        raise HTTPException(
            status_code=500, detail="Action proposal disappeared after cancellation"
        )
    return ActionMutationResponse(action=_to_action_response(store, refreshed))


@router.get("/sessions/{session_id}/artifacts/{artifact_id}")
def download_artifact(
    session_id: str,
    artifact_id: str,
    store: SQLiteStore = Depends(get_store),
    settings: AppSettings = Depends(get_app_settings),
) -> FileResponse:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    artifact = store.get_export_artifact(artifact_id)
    if artifact is None or artifact.session_id != session_id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    path = (settings.data_root / Path(artifact.file_path)).resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")
    return FileResponse(path, media_type=artifact.mime_type, filename=artifact.file_name)
