from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.api.routers import sessions as sessions_router  # noqa: E402
from backend.app.config import AppSettings  # noqa: E402
from backend.app.services.actions import ActionOrchestrator  # noqa: E402
from backend.app.store import (  # noqa: E402
    SQLiteStore,
    TranscriptSegmentInput,
    TranscriptSpeakerInput,
)


@dataclass
class _CancelCall:
    job_id: str
    reason: str


class FakeJobRuntime:
    def __init__(self) -> None:
        self.canceled: list[_CancelCall] = []

    def mark_canceled(self, job_id: str, *, reason: str = "canceled") -> None:
        self.canceled.append(_CancelCall(job_id=job_id, reason=reason))


def _test_settings(tmp_path: Path) -> AppSettings:
    data_root = tmp_path / "data"
    sessions_root = data_root / "sessions"
    db_path = data_root / "privata.db"
    data_root.mkdir(parents=True, exist_ok=True)
    sessions_root.mkdir(parents=True, exist_ok=True)
    return AppSettings(
        app_name="Transcibio Test",
        environment="test",
        host="127.0.0.1",
        port=8000,
        data_root=data_root,
        db_path=db_path,
        sessions_root=sessions_root,
        processing_profile="balanced",
        stt_provider="faster-whisper",
        llm_provider="none",
        tts_provider="piper",
        ffmpeg_required=False,
    )


def _make_app(
    *,
    store: SQLiteStore,
    settings: AppSettings,
    job_runtime: FakeJobRuntime,
) -> FastAPI:
    app = FastAPI()
    app.state.store = store
    app.state.settings = settings
    app.state.runtime = {"ffmpeg": {"available": False}}
    app.state.action_orchestrator = ActionOrchestrator(store=store, settings=settings)
    app.state.job_runtime = job_runtime
    app.include_router(sessions_router.router, prefix="/api/v1")
    return app


@pytest.fixture
def app_settings(tmp_path: Path) -> AppSettings:
    return _test_settings(tmp_path)


@pytest.fixture
def store(app_settings: AppSettings) -> SQLiteStore:
    s = SQLiteStore(app_settings.db_path)
    s.initialize()
    return s


@pytest.fixture
def job_runtime() -> FakeJobRuntime:
    return FakeJobRuntime()


@pytest.fixture
def client(
    store: SQLiteStore,
    app_settings: AppSettings,
    job_runtime: FakeJobRuntime,
) -> TestClient:
    return TestClient(_make_app(store=store, settings=app_settings, job_runtime=job_runtime))


def test_patch_session_rename_happy_path(client: TestClient) -> None:
    created = client.post("/api/v1/sessions", json={"title": "Original"})
    assert created.status_code == 200
    session_id = created.json()["id"]
    original_updated = created.json()["updated_at_utc"]

    response = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"title": "Renamed meeting"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == session_id
    assert body["title"] == "Renamed meeting"
    assert body["updated_at_utc"] != original_updated


def test_patch_session_rename_rejects_empty_title(client: TestClient) -> None:
    created = client.post("/api/v1/sessions", json={"title": "S"})
    session_id = created.json()["id"]
    response = client.patch(f"/api/v1/sessions/{session_id}", json={"title": ""})
    assert response.status_code == 422


def test_patch_session_rename_rejects_too_long_title(client: TestClient) -> None:
    created = client.post("/api/v1/sessions", json={"title": "S"})
    session_id = created.json()["id"]
    response = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"title": "x" * 201},
    )
    assert response.status_code == 422


def test_patch_session_rename_missing_returns_404(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/sessions/does-not-exist",
        json={"title": "Hello"},
    )
    assert response.status_code == 404


def test_delete_session_cascade_removes_rows(
    client: TestClient,
    store: SQLiteStore,
    app_settings: AppSettings,
) -> None:
    import sqlite3

    created = client.post("/api/v1/sessions", json={"title": "Deletable"})
    session_id = created.json()["id"]

    # Seed transcript + chat + audio + job so cascade has something to clean up.
    revision_result = store.create_transcript_revision(
        session_id=session_id,
        created_by="test",
        source="seed",
        full_text="hello",
        language_detected="en",
        diarization_used=False,
        stt_model="fake",
        warnings=[],
        speakers=[TranscriptSpeakerInput(speaker_key="S0", display_name="Speaker 1", sort_order=0)],
        segments=[
            TranscriptSegmentInput(
                segment_index=0,
                speaker_key="S0",
                start_ms=0,
                end_ms=1000,
                text="hello",
                word_count=1,
            ),
        ],
    )
    thread = store.get_or_create_chat_thread(session_id=session_id)
    store.create_chat_message(
        thread_id=thread.id,
        session_id=session_id,
        transcript_revision_id=revision_result.revision.id,
        role="user",
        content_markdown="hi",
        content_plain_text="hi",
        source_kind="typed",
        status="completed",
    )
    store.create_audio_asset(
        session_id=session_id,
        kind="meeting_audio",
        mime_type="audio/wav",
        file_path=f"sessions/{session_id}/audio/meeting.wav",
        duration_ms=1000,
    )
    job = store.create_job(
        job_type="transcribe_audio",
        session_id=session_id,
        input_payload={"session_id": session_id},
    )

    response = client.delete(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 204

    assert store.get_session(session_id) is None

    con = sqlite3.connect(app_settings.db_path)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        for table in (
            "transcript_revisions",
            "transcript_speakers",
            "transcript_segments",
            "chat_threads",
            "chat_messages",
            "audio_assets",
        ):
            count = con.execute(
                f"SELECT COUNT(*) FROM {table} WHERE session_id = ?"
                if table
                in ("transcript_revisions", "chat_threads", "chat_messages", "audio_assets")
                else f"SELECT COUNT(*) FROM {table}",
                (session_id,)
                if table
                in ("transcript_revisions", "chat_threads", "chat_messages", "audio_assets")
                else (),
            ).fetchone()[0]
            assert count == 0, f"orphan rows in {table}"
    finally:
        con.close()
    # Job row remains (no FK) but the API called mark_canceled on it.
    assert store.get_job(job.id) is not None


def test_delete_session_removes_session_directory(
    client: TestClient,
    store: SQLiteStore,
    app_settings: AppSettings,
) -> None:
    created = client.post("/api/v1/sessions", json={"title": "WithFiles"})
    session_id = created.json()["id"]
    session_dir = app_settings.sessions_root / session_id / "audio"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "meeting.wav").write_bytes(b"RIFF" + b"\x00" * 32)

    response = client.delete(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 204
    assert not (app_settings.sessions_root / session_id).exists()


def test_delete_session_missing_returns_404(client: TestClient) -> None:
    response = client.delete("/api/v1/sessions/missing")
    assert response.status_code == 404


def test_delete_session_cancels_running_jobs(
    client: TestClient,
    store: SQLiteStore,
    job_runtime: FakeJobRuntime,
) -> None:
    created = client.post("/api/v1/sessions", json={"title": "WithJobs"})
    session_id = created.json()["id"]
    running_job = store.create_job(
        job_type="transcribe_audio",
        session_id=session_id,
        input_payload={"session_id": session_id},
    )
    store.update_job(running_job.id, status="running", started=True)
    queued_job = store.create_job(
        job_type="chat_reply",
        session_id=session_id,
        input_payload={"session_id": session_id},
    )
    # A succeeded job in another session shouldn't be touched.
    other_session = client.post("/api/v1/sessions", json={"title": "Other"}).json()
    other_job = store.create_job(
        job_type="chat_reply",
        session_id=other_session["id"],
        input_payload={"session_id": other_session["id"]},
    )

    response = client.delete(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 204

    canceled_ids = {call.job_id for call in job_runtime.canceled}
    assert running_job.id in canceled_ids
    assert queued_job.id in canceled_ids
    assert other_job.id not in canceled_ids
    for call in job_runtime.canceled:
        assert call.reason == "session_deleted"
