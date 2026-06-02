from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.deps import get_job_runtime, get_store
from backend.app.services.job_runtime import JobRuntime
from backend.app.store import JobRecord, SQLiteStore

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    id: str
    session_id: str | None
    job_type: str
    status: str
    progress: float
    created_at_utc: str
    started_at_utc: str | None
    finished_at_utc: str | None
    input_json: dict
    output_json: dict
    error_message: str


class CreateFakeJobRequest(BaseModel):
    session_id: str | None = None
    steps: int = Field(default=5, ge=1, le=20)


class CreateFakeJobResponse(BaseModel):
    job_id: str
    status: str


def _parse_job_payload(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        parsed = json.loads(raw or "{}")
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Job payload must be a JSON object.")


def _to_job_response(record: JobRecord) -> JobResponse:
    payload = {
        "id": record.id,
        "session_id": record.session_id,
        "job_type": record.job_type,
        "status": record.status,
        "progress": record.progress,
        "created_at_utc": record.created_at_utc,
        "started_at_utc": record.started_at_utc,
        "finished_at_utc": record.finished_at_utc,
        "input_json": _parse_job_payload(record.input_json),
        "output_json": _parse_job_payload(record.output_json),
        "error_message": record.error_message,
    }
    return JobResponse.model_validate(payload)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, store: Annotated[SQLiteStore, Depends(get_store)]) -> JobResponse:
    record = store.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_job_response(record)


@router.post("/dev/fake", response_model=CreateFakeJobResponse)
def create_fake_job(
    payload: CreateFakeJobRequest,
    store: Annotated[SQLiteStore, Depends(get_store)],
    job_runtime: Annotated[JobRuntime, Depends(get_job_runtime)],
) -> CreateFakeJobResponse:
    if payload.session_id and store.get_session(payload.session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    job_id = job_runtime.enqueue_fake_progress_job(
        session_id=payload.session_id, steps=payload.steps
    )
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Job creation failed")
    return CreateFakeJobResponse(job_id=job_id, status=job.status)
