from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.api.routers import sessions as sessions_router  # noqa: E402
from backend.app.api.routers import settings as settings_router  # noqa: E402
from backend.app.config import AppSettings  # noqa: E402
from backend.app.services.stt_nemotron import nemotron_status_file  # noqa: E402
from backend.app.services.transcription_orchestrator import resolve_stt_engine  # noqa: E402
from backend.app.store import SQLiteStore  # noqa: E402


class FakeJobRuntime:
    """Captures transcription jobs instead of running them."""

    def __init__(self) -> None:
        self.enqueued: list[dict] = []

    def enqueue_transcription_job(self, **kwargs) -> str:
        self.enqueued.append(kwargs)
        return "job-1"

    def mark_canceled(self, job_id: str, *, reason: str = "canceled") -> None:
        pass


class FakeJobStore(SQLiteStore):
    def get_job(self, job_id: str):  # the fake runtime doesn't create a DB row
        class _Job:
            status = "queued"

        return _Job()


def _settings(tmp_path: Path) -> AppSettings:
    data_root = tmp_path / "data"
    (data_root / "sessions").mkdir(parents=True)
    return AppSettings(
        app_name="Transcibio Test",
        environment="test",
        host="127.0.0.1",
        port=8000,
        data_root=data_root,
        db_path=data_root / "privata.db",
        sessions_root=data_root / "sessions",
        processing_profile="balanced",
        stt_provider="faster-whisper",
        llm_provider="ollama",
        tts_provider="piper",
        ffmpeg_required=False,
    )


@pytest.fixture
def client_and_state(tmp_path: Path):
    settings = _settings(tmp_path)
    store = FakeJobStore(settings.db_path)
    store.initialize()
    runtime = FakeJobRuntime()
    app = FastAPI()
    app.state.store = store
    app.state.settings = settings
    app.state.job_runtime = runtime
    app.include_router(settings_router.router, prefix="/api/v1")
    app.include_router(sessions_router.router, prefix="/api/v1")
    return TestClient(app), store, runtime


def test_engine_defaults_to_whisper_pyannote(client_and_state):
    client, store, _ = client_and_state
    assert client.get("/api/v1/settings").json()["stt"]["engine"] == "whisper-pyannote"
    assert resolve_stt_engine(store) == "whisper-pyannote"


def test_engine_patch_round_trip(client_and_state):
    client, store, _ = client_and_state
    response = client.patch("/api/v1/settings", json={"stt": {"engine": "nemotron"}})
    assert response.status_code == 200
    assert response.json()["stt"]["engine"] == "nemotron"
    assert client.get("/api/v1/settings").json()["stt"]["engine"] == "nemotron"
    # Other stt settings survive the patch.
    assert client.get("/api/v1/settings").json()["stt"]["diarization_enabled_default"] is True
    assert resolve_stt_engine(store) == "nemotron"


def test_engine_patch_rejects_unknown_engine(client_and_state):
    client, _, _ = client_and_state
    response = client.patch("/api/v1/settings", json={"stt": {"engine": "whisperx"}})
    assert response.status_code == 422


def test_transcription_job_records_engine_at_queue_time(client_and_state):
    client, store, runtime = client_and_state
    session = store.create_session(title="t", source_kind="upload")
    asset = store.create_audio_asset(
        session_id=session.id,
        kind="meeting_audio",
        mime_type="audio/wav",
        file_path="sessions/x/audio/a.wav",
        duration_ms=1000,
        sample_rate_hz=16000,
        channels=1,
    )
    client.patch("/api/v1/settings", json={"stt": {"engine": "nemotron"}})
    response = client.post(
        f"/api/v1/sessions/{session.id}/transcription-jobs",
        json={"audio_asset_id": asset.id},
    )
    assert response.status_code == 200
    assert runtime.enqueued[-1]["stt_engine"] == "nemotron"


def test_chat_think_patch_round_trip(client_and_state, monkeypatch):
    monkeypatch.delenv("TRANSCIBIO_OLLAMA_THINK", raising=False)
    client, _, _ = client_and_state
    assert client.get("/api/v1/settings").json()["chat"]["think"] is False
    response = client.patch("/api/v1/settings", json={"chat": {"think": True}})
    assert response.status_code == 200 and response.json()["chat"]["think"] is True
    assert client.get("/api/v1/settings").json()["chat"]["think"] is True


def _session_with_audio(store):
    session = store.create_session(title="t", source_kind="upload")
    asset = store.create_audio_asset(
        session_id=session.id,
        kind="meeting_audio",
        mime_type="audio/wav",
        file_path="sessions/x/audio/a.wav",
        duration_ms=1000,
        sample_rate_hz=16000,
        channels=1,
    )
    return session, asset


def test_job_uses_saved_transcription_settings_when_request_omits_them(client_and_state):
    client, store, runtime = client_and_state
    session, asset = _session_with_audio(store)
    client.patch(
        "/api/v1/settings",
        json={"stt": {"default_preset": "quality", "diarization_enabled_default": False}},
    )
    client.post(
        f"/api/v1/sessions/{session.id}/transcription-jobs", json={"audio_asset_id": asset.id}
    )
    job = runtime.enqueued[-1]
    assert job["stt_preset"] == "quality"
    assert job["diarization_enabled"] is False
    assert job["language_hint"] == "auto"
    assert job["stt_engine"] == "whisper-pyannote"


def test_explicit_request_values_win_over_settings(client_and_state):
    client, store, runtime = client_and_state
    session, asset = _session_with_audio(store)
    client.patch("/api/v1/settings", json={"stt": {"default_preset": "quality"}})
    client.post(
        f"/api/v1/sessions/{session.id}/transcription-jobs",
        json={"audio_asset_id": asset.id, "stt_preset": "fast", "diarization_enabled": True},
    )
    job = runtime.enqueued[-1]
    assert job["stt_preset"] == "fast" and job["diarization_enabled"] is True


def _closed_local_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_nemotron_status_reports_starting_from_heartbeat(client_and_state, monkeypatch):
    client, _, _ = client_and_state
    url = f"http://127.0.0.1:{_closed_local_port()}/v1/chat/completions"
    monkeypatch.setenv("TRANSCIBIO_NEMOTRON_URL", url)

    stopped = client.get("/api/v1/settings/nemotron-status").json()
    assert stopped["state"] == "stopped"
    assert stopped["reachable"] is False
    assert stopped["starting_seconds"] is None

    data_root = client.app.state.settings.data_root
    status_file = nemotron_status_file(data_root)
    status_file.parent.mkdir(parents=True)
    status_file.write_text(json.dumps({"started_at": time.time() - 90}), encoding="utf-8")

    starting = client.get("/api/v1/settings/nemotron-status").json()
    assert starting["state"] == "starting"
    assert 89 <= starting["starting_seconds"] <= 95
