from __future__ import annotations

import json
import queue

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.api.deps import get_job_runtime, get_store
from backend.app.services.job_runtime import JobEvent, JobRuntime
from backend.app.store import SQLiteStore

router = APIRouter(prefix="/events", tags=["events"])


def _format_sse(event: JobEvent) -> str:
    payload = json.dumps(event.to_dict(), ensure_ascii=False)
    return f"event: {event.type}\ndata: {payload}\n\n"


@router.get("/jobs/{job_id}")
def stream_job_events(
    job_id: str,
    store: SQLiteStore = Depends(get_store),
    job_runtime: JobRuntime = Depends(get_job_runtime),
) -> StreamingResponse:
    if store.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    def event_stream():
        # Subscribe inside the generator so that if the generator is never
        # iterated (e.g. client disconnects before StreamingResponse consumes
        # it), no subscriber is registered and thus none can leak.
        subscriber = job_runtime.subscribe(job_id)
        try:
            snapshot = store.get_job(job_id)
            if snapshot is not None:
                snapshot_event = JobEvent(
                    type="job.snapshot",
                    job_id=job_id,
                    timestamp=snapshot.created_at_utc,
                    payload={
                        "status": snapshot.status,
                        "progress": snapshot.progress,
                        "error_message": snapshot.error_message,
                    },
                )
                yield _format_sse(snapshot_event)

                if snapshot.status in {"succeeded", "failed"}:
                    terminal_event = JobEvent(
                        type=f"job.{snapshot.status}",
                        job_id=job_id,
                        timestamp=snapshot.finished_at_utc or snapshot.created_at_utc,
                        payload={
                            "status": snapshot.status,
                            "progress": snapshot.progress,
                            "error_message": snapshot.error_message,
                            "output_json": snapshot.output_json,
                        },
                    )
                    yield _format_sse(terminal_event)
                    return

            while True:
                try:
                    event = subscriber.get(timeout=15)
                except queue.Empty:
                    keepalive = JobEvent(
                        type="keepalive",
                        job_id=job_id,
                        timestamp=snapshot.created_at_utc if snapshot else "",
                        payload={},
                    )
                    yield _format_sse(keepalive)
                    continue

                yield _format_sse(event)
                if event.type in {"job.succeeded", "job.failed"}:
                    break
        finally:
            job_runtime.unsubscribe(job_id, subscriber)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
