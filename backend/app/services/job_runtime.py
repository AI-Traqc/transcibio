from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from backend.app.config import AppSettings
from backend.app.services.chat_orchestrator import ChatOrchestrator, ChatReplyJobInput
from backend.app.services.local_llm import resolve_local_llm_config
from backend.app.services.title_generation import generate_session_title
from backend.app.services.transcription_orchestrator import (
    TranscriptionJobInput,
    TranscriptionOrchestrator,
)
from backend.app.store import SQLiteStore

_LOGGER = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class JobEvent:
    type: str
    job_id: str
    timestamp: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobRuntime:
    """In-process background job runner with pub/sub for SSE."""

    def __init__(
        self,
        store: SQLiteStore,
        *,
        transcription_orchestrator: TranscriptionOrchestrator | None = None,
        chat_orchestrator: ChatOrchestrator | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        self._store = store
        self._transcription_orchestrator = transcription_orchestrator
        self._chat_orchestrator = chat_orchestrator
        self._settings = settings
        self._queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._subscribers: dict[str, list[queue.Queue[JobEvent]]] = {}
        self._sub_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="transcibio-jobs"
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        self._queue.put(("", {}))
        if self._thread:
            self._thread.join(timeout=timeout)

    def enqueue_fake_progress_job(self, *, session_id: str | None = None, steps: int = 5) -> str:
        job = self._store.create_job(
            job_type="demo_fake_progress",
            session_id=session_id,
            input_payload={"steps": max(1, min(steps, 20))},
        )
        self._publish("job.queued", job.id, {"status": job.status, "progress": job.progress})
        self._queue.put((job.id, {"steps": max(1, min(steps, 20))}))
        return job.id

    def enqueue_transcription_job(
        self,
        *,
        session_id: str,
        audio_asset_id: str,
        language_hint: str = "auto",
        stt_preset: str = "balanced",
        diarization_enabled: bool = True,
    ) -> str:
        job = self._store.create_job(
            job_type="transcribe_audio",
            session_id=session_id,
            input_payload={
                "session_id": session_id,
                "audio_asset_id": audio_asset_id,
                "language_hint": language_hint,
                "stt_preset": stt_preset,
                "diarization_enabled": bool(diarization_enabled),
            },
        )
        self._publish("job.queued", job.id, {"status": job.status, "progress": job.progress})
        self._queue.put(
            (
                job.id,
                {
                    "session_id": session_id,
                    "audio_asset_id": audio_asset_id,
                    "language_hint": language_hint,
                    "stt_preset": stt_preset,
                    "diarization_enabled": bool(diarization_enabled),
                },
            )
        )
        return job.id

    def enqueue_chat_reply_job(
        self,
        *,
        session_id: str,
        thread_id: str,
        user_message_id: str,
        assistant_message_id: str,
        transcript_revision_id: str | None,
    ) -> str:
        job = self._store.create_job(
            job_type="chat_reply",
            session_id=session_id,
            input_payload={
                "session_id": session_id,
                "thread_id": thread_id,
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
                "transcript_revision_id": transcript_revision_id or "",
            },
        )
        self._publish("job.queued", job.id, {"status": job.status, "progress": job.progress})
        self._queue.put(
            (
                job.id,
                {
                    "session_id": session_id,
                    "thread_id": thread_id,
                    "user_message_id": user_message_id,
                    "assistant_message_id": assistant_message_id,
                    "transcript_revision_id": transcript_revision_id or "",
                },
            )
        )
        return job.id

    def mark_canceled(self, job_id: str, *, reason: str = "canceled") -> None:
        """Mark a job as failed with a cancellation reason and notify subscribers.

        Does not stop the worker thread if already mid-run; the orchestrator is
        expected to early-exit on a missing session.
        """
        record = self._store.get_job(job_id)
        if record is None:
            return
        if record.status in ("succeeded", "failed", "canceled"):
            return
        self._store.update_job(
            job_id,
            status="failed",
            error_message=reason,
            finished=True,
        )
        self._publish(
            "job.failed",
            job_id,
            {"status": "failed", "progress": record.progress, "error_message": reason},
        )

    def subscribe(self, job_id: str) -> queue.Queue[JobEvent]:
        q: queue.Queue[JobEvent] = queue.Queue()
        with self._sub_lock:
            self._subscribers.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, subscriber: queue.Queue[JobEvent]) -> None:
        with self._sub_lock:
            listeners = self._subscribers.get(job_id, [])
            if subscriber in listeners:
                listeners.remove(subscriber)
            if not listeners and job_id in self._subscribers:
                self._subscribers.pop(job_id, None)

    def _publish(self, event_type: str, job_id: str, payload: dict[str, Any]) -> None:
        event = JobEvent(type=event_type, job_id=job_id, timestamp=_utc_now_iso(), payload=payload)
        with self._sub_lock:
            listeners = list(self._subscribers.get(job_id, []))
        for listener in listeners:
            listener.put(event)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id, payload = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if not job_id:
                continue
            try:
                self._run_job(job_id=job_id, payload=payload)
            except Exception as exc:  # pragma: no cover - foundation fallback
                record_snapshot = self._store.get_job(job_id)
                if (
                    record_snapshot is not None
                    and record_snapshot.job_type == "transcribe_audio"
                    and record_snapshot.session_id
                ):
                    try:
                        self._store.update_session_status(
                            record_snapshot.session_id,
                            status="error",
                            last_error=str(exc),
                        )
                    except Exception:
                        _LOGGER.exception(
                            "Failed to mark session %s as errored for job %s",
                            record_snapshot.session_id,
                            job_id,
                        )
                if record_snapshot is not None and record_snapshot.job_type == "chat_reply":
                    try:
                        assistant_id = json.loads(record_snapshot.input_json).get(
                            "assistant_message_id"
                        )
                        if isinstance(assistant_id, str) and assistant_id:
                            self._store.update_chat_message(
                                assistant_id,
                                status="failed",
                                metadata={"error": str(exc)},
                            )
                    except Exception:
                        _LOGGER.exception(
                            "Failed to mark assistant message as failed for job %s", job_id
                        )
                record = self._store.update_job(
                    job_id,
                    status="failed",
                    error_message=str(exc),
                    finished=True,
                )
                self._publish(
                    "job.failed",
                    job_id,
                    {
                        "status": record.status,
                        "progress": record.progress,
                        "error_message": str(exc),
                    },
                )

    def _run_job(self, *, job_id: str, payload: dict[str, Any]) -> None:
        record = self._store.get_job(job_id)
        if record is None:
            raise KeyError(f"Job not found: {job_id}")
        if record.job_type == "demo_fake_progress":
            self._run_fake_progress(job_id=job_id, steps=int(payload.get("steps", 5)))
            return
        if record.job_type == "transcribe_audio":
            self._run_transcription_job(job_id=job_id, payload=payload)
            return
        if record.job_type == "chat_reply":
            self._run_chat_reply_job(job_id=job_id, payload=payload)
            return
        raise RuntimeError(f"Unsupported job type: {record.job_type}")

    def _run_fake_progress(self, *, job_id: str, steps: int) -> None:
        record = self._store.update_job(job_id, status="running", started=True)
        self._publish("job.started", job_id, {"status": record.status, "progress": record.progress})
        for idx in range(max(1, steps)):
            if self._stop_event.is_set():
                break
            progress = round((idx + 1) / max(1, steps), 4)
            time.sleep(0.2)
            record = self._store.update_job(job_id, progress=progress, status="running")
            self._publish(
                "job.progress",
                job_id,
                {
                    "status": record.status,
                    "progress": record.progress,
                    "step": idx + 1,
                    "steps": steps,
                },
            )
        record = self._store.update_job(
            job_id,
            status="succeeded",
            progress=1.0,
            output_payload={"message": "Demo job completed"},
            finished=True,
        )
        self._publish(
            "job.succeeded",
            job_id,
            {
                "status": record.status,
                "progress": record.progress,
                "output_json": record.output_json,
            },
        )

    def _run_transcription_job(self, *, job_id: str, payload: dict[str, Any]) -> None:
        if self._transcription_orchestrator is None:
            raise RuntimeError("Transcription orchestrator is not configured.")

        session_id = str(payload["session_id"])
        self._store.update_session_status(session_id, status="processing", last_error="")

        record = self._store.update_job(job_id, status="running", started=True, progress=0.02)
        self._publish("job.started", job_id, {"status": record.status, "progress": record.progress})

        def emit(event_type: str, event_payload: dict[str, Any]) -> None:
            progress_value = event_payload.get("progress")
            if isinstance(progress_value, (int, float)):
                updated = self._store.update_job(
                    job_id, status="running", progress=float(progress_value)
                )
                event_payload = {
                    **event_payload,
                    "status": updated.status,
                    "progress": updated.progress,
                }
            self._publish(event_type, job_id, event_payload)

        result = self._transcription_orchestrator.transcribe_audio_asset(
            TranscriptionJobInput(
                session_id=session_id,
                audio_asset_id=str(payload["audio_asset_id"]),
                language_hint=str(payload.get("language_hint", "auto")),  # validated downstream
                stt_preset=str(payload.get("stt_preset", "balanced")),  # validated downstream
                diarization_enabled=bool(payload.get("diarization_enabled", True)),
            ),
            on_event=emit,
        )

        final_record = self._store.update_job(
            job_id,
            status="succeeded",
            progress=1.0,
            output_payload=result.to_dict(),
            finished=True,
        )
        self._publish(
            "job.succeeded",
            job_id,
            {
                "status": final_record.status,
                "progress": final_record.progress,
                "output_json": final_record.output_json,
            },
        )

        self._try_generate_session_title(session_id, result)

    def _try_generate_session_title(self, session_id: str, result: Any) -> None:
        try:
            revision_id = getattr(result, "transcript_revision_id", "")
            if not revision_id:
                return
            revision = self._store.get_transcript_revision(revision_id)
            if revision is None or not revision.full_text.strip():
                return
            model_name = ""
            if self._settings:
                llm_config = resolve_local_llm_config(store=self._store, settings=self._settings)
                model_name = llm_config.model_name
            generate_session_title(
                revision.full_text,
                store=self._store,
                session_id=session_id,
                model_name=model_name,
            )
        except Exception:
            # Title generation is best-effort; log but never fail the transcription job.
            _LOGGER.warning("Session title generation failed for %s", session_id, exc_info=True)

    def _run_chat_reply_job(self, *, job_id: str, payload: dict[str, Any]) -> None:
        if self._chat_orchestrator is None:
            raise RuntimeError("Chat orchestrator is not configured.")

        record = self._store.update_job(job_id, status="running", started=True, progress=0.05)
        self._publish("job.started", job_id, {"status": record.status, "progress": record.progress})

        def emit(event_type: str, event_payload: dict[str, Any]) -> None:
            progress_value = event_payload.get("progress")
            if isinstance(progress_value, (int, float)):
                updated = self._store.update_job(
                    job_id, status="running", progress=float(progress_value)
                )
                event_payload = {
                    **event_payload,
                    "status": updated.status,
                    "progress": updated.progress,
                }
            self._publish(event_type, job_id, event_payload)

        result = self._chat_orchestrator.run_chat_reply_job(
            ChatReplyJobInput(
                session_id=str(payload["session_id"]),
                thread_id=str(payload["thread_id"]),
                user_message_id=str(payload["user_message_id"]),
                assistant_message_id=str(payload["assistant_message_id"]),
                transcript_revision_id=(
                    str(payload.get("transcript_revision_id")).strip() or None
                    if payload.get("transcript_revision_id") is not None
                    else None
                ),
            ),
            on_event=emit,
        )

        final_record = self._store.update_job(
            job_id,
            status="succeeded",
            progress=1.0,
            output_payload=result.to_dict(),
            finished=True,
        )
        self._publish(
            "job.succeeded",
            job_id,
            {
                "status": final_record.status,
                "progress": final_record.progress,
                "output_json": final_record.output_json,
            },
        )
