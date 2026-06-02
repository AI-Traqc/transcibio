from __future__ import annotations

import io
import json
import wave
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.config import AppSettings
from backend.app.services.actions import ActionOrchestrator
from backend.app.services.chat_orchestrator import ChatOrchestrator, ChatReplyJobInput
from backend.app.services.retrieval import TranscriptRetriever
from backend.app.services.tts import TtsUnavailableError
from backend.app.store import SQLiteStore, TranscriptSegmentInput, TranscriptSpeakerInput

pytest.importorskip("fastapi")
pytest.importorskip("multipart")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.api.routers import actions as actions_router  # noqa: E402
from backend.app.api.routers import sessions as sessions_router  # noqa: E402
from backend.app.api.routers import settings as settings_router  # noqa: E402
from backend.app.api.routers import tts as tts_router  # noqa: E402
from backend.app.api.routers import voice_commands as voice_commands_router  # noqa: E402
from backend.app.services.tts import TtsOrchestrator  # noqa: E402


@dataclass(frozen=True)
class FakeStoredAudio:
    mime_type: str
    relative_path: str
    duration_ms: int
    sample_rate_hz: int | None
    channels: int | None


class FakeJobRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def enqueue_chat_reply_job(
        self,
        *,
        session_id: str,
        thread_id: str,
        user_message_id: str,
        assistant_message_id: str,
        transcript_revision_id: str,
    ) -> str:
        self.calls.append(
            {
                "session_id": session_id,
                "thread_id": thread_id,
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
                "transcript_revision_id": transcript_revision_id,
            }
        )
        return "job_fake_voice_auto_send"


class FakeTtsClientSuccess:
    def synthesize_to_wav(
        self, *, text: str, output_path: Path, voice: str | None = None, speed: float = 1.0
    ):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\x00\x00" * 1600)
        return SimpleNamespace(
            output_path=output_path, model_name=f"piper-test:{voice or 'default'}"
        )


class FakeTtsClientUnavailable:
    def synthesize_to_wav(
        self, *, text: str, output_path: Path, voice: str | None = None, speed: float = 1.0
    ):
        raise TtsUnavailableError("Piper binary not found in PATH (optional TTS dependency).")


class FakeVoiceAudioStorageService:
    def __init__(self, *, settings: AppSettings, session_id: str) -> None:
        self._settings = settings
        self._session_id = session_id

    def save_recording_upload(
        self,
        *,
        session_id: str,
        filename: str,
        content_type: str | None,
        fileobj,
        max_duration_ms: int,
        normalize_sample_rate_hz: int | None,
    ) -> FakeStoredAudio:
        assert session_id == self._session_id
        rel = f"sessions/{session_id}/audio/{filename}"
        path = self._settings.data_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = fileobj.read()
        path.write_bytes(data if isinstance(data, (bytes, bytearray)) else b"fake")
        return FakeStoredAudio(
            mime_type="audio/wav",
            relative_path=rel,
            duration_ms=700,
            sample_rate_hz=16000,
            channels=1,
        )


@dataclass(frozen=True)
class FakeCommandSttResult:
    text: str
    detected_language: str
    model_name: str


class FakeCommandSttClient:
    def __init__(self, text: str = "Please draft an email follow-up") -> None:
        self._text = text

    def transcribe_command(self, audio_path, *, language_hint="auto", preset=None):
        return FakeCommandSttResult(
            text=self._text, detected_language="en", model_name="fake-command-stt"
        )


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


@pytest.fixture
def app_settings(tmp_path: Path) -> AppSettings:
    return _test_settings(tmp_path)


@pytest.fixture
def store(app_settings: AppSettings) -> SQLiteStore:
    store = SQLiteStore(app_settings.db_path)
    store.initialize()
    return store


def _seed_transcript(store: SQLiteStore, session_id: str, *, texts: list[str] | None = None):
    segment_texts = texts or ["hello   team !!", "we should send an email and task list"]
    speakers = [
        TranscriptSpeakerInput(speaker_key="SPEAKER_00", display_name="Speaker 1", sort_order=0)
    ]
    segments = [
        TranscriptSegmentInput(
            segment_index=index,
            speaker_key="SPEAKER_00",
            start_ms=index * 5000,
            end_ms=(index + 1) * 5000 - 1,
            text=text,
            word_count=max(1, len(text.split())),
        )
        for index, text in enumerate(segment_texts)
    ]
    return store.create_transcript_revision(
        session_id=session_id,
        created_by="test",
        source="seed",
        full_text="\n".join(segment_texts),
        language_detected="en",
        diarization_used=False,
        stt_model="fake-stt",
        warnings=[],
        speakers=speakers,
        segments=segments,
    )


def _seed_chat_thread_with_assistant(
    store: SQLiteStore, session_id: str, revision_id: str | None = None
):
    thread = store.get_or_create_chat_thread(session_id=session_id)
    user = store.create_chat_message(
        thread_id=thread.id,
        session_id=session_id,
        transcript_revision_id=revision_id,
        role="user",
        content_markdown="Please draft an email and task list",
        content_plain_text="Please draft an email and task list",
        source_kind="typed",
        status="completed",
    )
    assistant = store.create_chat_message(
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
    return thread, user, assistant


def _make_test_app(
    *,
    store: SQLiteStore,
    settings: AppSettings,
    tts_client=None,
    include_sessions: bool = False,
    include_tts: bool = False,
    include_settings: bool = False,
    include_actions: bool = False,
    include_voice_commands: bool = False,
    job_runtime=None,
) -> FastAPI:
    app = FastAPI()
    app.state.store = store
    app.state.settings = settings
    app.state.runtime = {"ffmpeg": {"available": False}}
    app.state.action_orchestrator = ActionOrchestrator(store=store, settings=settings)
    app.state.tts_orchestrator = TtsOrchestrator(
        store=store, settings=settings, tts_client=tts_client
    )
    app.state.job_runtime = job_runtime or FakeJobRuntime()
    if include_sessions:
        app.include_router(sessions_router.router, prefix="/api/v1")
    if include_tts:
        app.include_router(tts_router.router, prefix="/api/v1")
    if include_settings:
        app.include_router(settings_router.router, prefix="/api/v1")
    if include_actions:
        app.include_router(actions_router.router, prefix="/api/v1")
    if include_voice_commands:
        app.include_router(voice_commands_router.router, prefix="/api/v1")
    return app


def test_settings_get_patch_and_persist_across_restart(tmp_path: Path):
    settings = _test_settings(tmp_path)
    store = SQLiteStore(settings.db_path)
    store.initialize()

    app1 = _make_test_app(store=store, settings=settings, include_settings=True)
    client1 = TestClient(app1)
    initial = client1.get("/api/v1/settings")
    assert initial.status_code == 200
    body = initial.json()
    assert body["processing_profile"] == "balanced"
    assert body["voice_commands"]["default_send_mode"] == "review_then_send"

    patched = client1.patch(
        "/api/v1/settings",
        json={
            "voice_commands": {"default_send_mode": "auto_send"},
            "tts": {"enabled": True, "auto_generate_on_chat_reply": True},
            "chat": {"llm_provider": "none", "response_detail": "brief"},
        },
    )
    assert patched.status_code == 200
    patched_json = patched.json()
    assert patched_json["voice_commands"]["default_send_mode"] == "auto_send"
    assert patched_json["tts"]["enabled"] is True
    assert patched_json["chat"]["response_detail"] == "brief"

    store_reopened = SQLiteStore(settings.db_path)
    store_reopened.initialize()
    app2 = _make_test_app(store=store_reopened, settings=settings, include_settings=True)
    client2 = TestClient(app2)
    reopened = client2.get("/api/v1/settings")
    assert reopened.status_code == 200
    reopened_json = reopened.json()
    assert reopened_json["voice_commands"]["default_send_mode"] == "auto_send"
    assert reopened_json["tts"]["auto_generate_on_chat_reply"] is True


def test_transcript_correction_proposal_and_apply_creates_revision_and_audit(
    store: SQLiteStore, app_settings: AppSettings
):
    session = store.create_session(title="Correction test", source_kind="upload")
    seeded = _seed_transcript(
        store, session.id, texts=["hello   team !!", "we  need a follow up email  ."]
    )
    app = _make_test_app(store=store, settings=app_settings, include_sessions=True)
    client = TestClient(app)

    proposal_resp = client.post(
        f"/api/v1/sessions/{session.id}/transcript/correction-proposals",
        json={
            "scope_type": "full_transcript",
            "strategy": "rules",
            "revision_id": seeded.revision.id,
        },
    )
    assert proposal_resp.status_code == 200
    proposal = proposal_resp.json()
    assert proposal["changed_segment_count"] >= 1
    assert "unified_diff_lines" in proposal["diff_preview"]

    apply_resp = client.post(
        f"/api/v1/sessions/{session.id}/transcript/correction-proposals/{proposal['proposal_id']}/apply"
    )
    assert apply_resp.status_code == 200
    payload = apply_resp.json()
    assert payload["status"] == "applied"
    assert payload["revision_number"] == 2
    assert payload["transcript"]["revision"]["revision_number"] == 2

    with store._connect() as con:  # noqa: SLF001 - test-only verification
        row = con.execute(
            """
            SELECT operation_type, payload_json
            FROM transcript_edit_operations
            WHERE session_id = ?
            ORDER BY created_at_utc DESC
            LIMIT 1
            """,
            (session.id,),
        ).fetchone()
    assert row is not None
    assert row["operation_type"] == "ai_correction_apply"
    operation_payload = json.loads(row["payload_json"])
    assert operation_payload["proposal_id"] == proposal["proposal_id"]


def test_transcript_correction_noop_warning_and_stale_apply_conflict(
    store: SQLiteStore, app_settings: AppSettings
):
    session = store.create_session(title="Correction noop", source_kind="upload")
    seeded = _seed_transcript(
        store, session.id, texts=["Hello team!", "We need a follow up email."]
    )
    app = _make_test_app(store=store, settings=app_settings, include_sessions=True)
    client = TestClient(app)

    noop = client.post(
        f"/api/v1/sessions/{session.id}/transcript/correction-proposals",
        json={
            "scope_type": "full_transcript",
            "strategy": "rules",
            "revision_id": seeded.revision.id,
        },
    )
    assert noop.status_code == 200
    noop_body = noop.json()
    assert noop_body["changed_segment_count"] == 0
    assert any("No correction changes" in item for item in noop_body["warnings"])

    segments = store.list_transcript_segments(seeded.revision.id)
    store.create_transcript_revision_from_text_overrides(
        session_id=session.id,
        base_revision_id=seeded.revision.id,
        segment_text_overrides={segments[0].id: "Hello team, updated."},
        actor="tester",
        source="manual_edit",
        operation_type="manual_segment_edit",
        operation_payload={"segment_id": segments[0].id},
    )
    stale_apply = client.post(
        f"/api/v1/sessions/{session.id}/transcript/correction-proposals/{noop_body['proposal_id']}/apply"
    )
    assert stale_apply.status_code == 409
    assert "Regenerate and try again" in stale_apply.json()["detail"]


def test_tts_api_unavailable_and_success_paths(store: SQLiteStore, app_settings: AppSettings):
    session = store.create_session(title="TTS test", source_kind="upload")
    transcript = _seed_transcript(store, session.id)
    thread = store.get_or_create_chat_thread(session_id=session.id)
    assistant = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=transcript.revision.id,
        role="assistant",
        content_markdown="Hello from TTS test.",
        content_plain_text="Hello from TTS test.",
        source_kind="assistant_reply",
        status="completed",
    )

    app_unavailable = _make_test_app(
        store=store,
        settings=app_settings,
        include_tts=True,
        tts_client=FakeTtsClientUnavailable(),
    )
    client_unavailable = TestClient(app_unavailable)
    failed = client_unavailable.post(
        f"/api/v1/sessions/{session.id}/tts",
        json={"message_id": assistant.id},
    )
    assert failed.status_code == 200
    failed_body = failed.json()
    assert failed_body["status"] == "failed"
    assert "Piper" in failed_body["error_message"]

    app_success = _make_test_app(
        store=store,
        settings=app_settings,
        include_tts=True,
        tts_client=FakeTtsClientSuccess(),
    )
    client_success = TestClient(app_success)
    generated = client_success.post(
        f"/api/v1/sessions/{session.id}/tts",
        json={"message_id": assistant.id, "force_regenerate": True},
    )
    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "succeeded"
    assert body["audio_asset_id"]
    assert body["download_url"].endswith(f"/tts/{assistant.id}/audio")

    status = client_success.get(f"/api/v1/sessions/{session.id}/tts/{assistant.id}")
    assert status.status_code == 200
    assert status.json()["status"] == "succeeded"

    audio = client_success.get(f"/api/v1/sessions/{session.id}/tts/{assistant.id}/audio")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")
    assert len(audio.content) > 32


def test_actions_confirm_exports_for_all_types_and_invalid_transitions(
    store: SQLiteStore, app_settings: AppSettings
):
    session = store.create_session(title="Action test", source_kind="upload")
    thread = store.get_or_create_chat_thread(session_id=session.id)
    message = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=None,
        role="assistant",
        content_markdown="Draft actions.",
        content_plain_text="Draft actions.",
        source_kind="assistant_reply",
        status="completed",
    )
    orchestrator = ActionOrchestrator(store=store, settings=app_settings)

    action_payloads = [
        ("email_draft", "Email", {"subject": "Hi", "body_markdown": "Hello"}),
        ("task_draft", "Tasks", {"tasks": ["One", "Two"]}),
        ("note_export", "Note", {"title": "Note", "body_markdown": "Body"}),
        ("doc_export", "Doc", {"title": "Doc", "body_markdown": "Body"}),
    ]
    created_actions = []
    for action_type, title, payload in action_payloads:
        created_actions.append(
            store.create_action_proposal(
                session_id=session.id,
                thread_id=thread.id,
                message_id=message.id,
                action_type=action_type,
                title=title,
                payload=payload,
                preview_markdown="Preview",
            )
        )

    for action in created_actions:
        result = orchestrator.confirm_action(session_id=session.id, action_id=action.id)
        assert result.action.status == "executed"
        assert len(result.artifacts) >= 1

    executed_again = orchestrator.confirm_action(
        session_id=session.id, action_id=created_actions[0].id
    )
    assert executed_again.action.status == "executed"

    with pytest.raises(ValueError):
        orchestrator.cancel_action(session_id=session.id, action_id=created_actions[0].id)

    cancel_candidate = store.create_action_proposal(
        session_id=session.id,
        thread_id=thread.id,
        message_id=message.id,
        action_type="task_draft",
        title="Cancel me",
        payload={"tasks": ["X"]},
        preview_markdown="Preview",
    )
    canceled = orchestrator.cancel_action(session_id=session.id, action_id=cancel_candidate.id)
    assert canceled.action.status == "canceled"
    with pytest.raises(ValueError):
        orchestrator.confirm_action(session_id=session.id, action_id=cancel_candidate.id)


def test_artifact_download_respects_session_ownership(
    store: SQLiteStore, app_settings: AppSettings
):
    session_a = store.create_session(title="A", source_kind="upload")
    session_b = store.create_session(title="B", source_kind="upload")
    thread = store.get_or_create_chat_thread(session_id=session_a.id)
    message = store.create_chat_message(
        thread_id=thread.id,
        session_id=session_a.id,
        transcript_revision_id=None,
        role="assistant",
        content_markdown="Doc",
        content_plain_text="Doc",
        source_kind="assistant_reply",
        status="completed",
    )
    action = store.create_action_proposal(
        session_id=session_a.id,
        thread_id=thread.id,
        message_id=message.id,
        action_type="doc_export",
        title="Doc",
        payload={"title": "Doc", "body_markdown": "Body"},
        preview_markdown="Body",
    )
    orch = ActionOrchestrator(store=store, settings=app_settings)
    confirm = orch.confirm_action(session_id=session_a.id, action_id=action.id)
    artifact = confirm.artifacts[0]

    app = _make_test_app(store=store, settings=app_settings, include_actions=True)
    client = TestClient(app)
    wrong = client.get(f"/api/v1/sessions/{session_b.id}/artifacts/{artifact.id}")
    assert wrong.status_code == 404
    ok = client.get(f"/api/v1/sessions/{session_a.id}/artifacts/{artifact.id}")
    assert ok.status_code == 200
    assert len(ok.content) > 0


def test_voice_command_review_and_auto_send_modes(
    store: SQLiteStore, app_settings: AppSettings, monkeypatch: pytest.MonkeyPatch
):
    session = store.create_session(title="Voice", source_kind="upload")
    seeded = _seed_transcript(store, session.id)
    fake_runtime = FakeJobRuntime()
    app = _make_test_app(
        store=store,
        settings=app_settings,
        include_voice_commands=True,
        job_runtime=fake_runtime,
    )
    client = TestClient(app)

    monkeypatch.setattr(
        voice_commands_router,
        "_audio_service_from_runtime",
        lambda settings, runtime_info: FakeVoiceAudioStorageService(
            settings=settings, session_id=session.id
        ),
    )
    monkeypatch.setattr(
        voice_commands_router,
        "FasterWhisperSttClient",
        lambda: FakeCommandSttClient("Review this command"),
    )

    review = client.post(
        f"/api/v1/sessions/{session.id}/voice-commands",
        files={"audio_file": ("cmd.wav", io.BytesIO(b"RIFFfake"), "audio/wav")},
        data={"send_mode": "review_then_send", "language_hint": "en"},
    )
    assert review.status_code == 200
    review_body = review.json()
    assert review_body["send_mode"] == "review_then_send"
    assert review_body["transcription_empty"] is False
    assert review_body["job_id"] is None
    assert fake_runtime.calls == []
    voice_rows = store.list_voice_commands(session.id)
    assert len(voice_rows) >= 1

    monkeypatch.setattr(
        voice_commands_router,
        "FasterWhisperSttClient",
        lambda: FakeCommandSttClient("Auto send this command"),
    )
    auto = client.post(
        f"/api/v1/sessions/{session.id}/voice-commands",
        files={"audio_file": ("cmd2.wav", io.BytesIO(b"RIFFfake2"), "audio/wav")},
        data={"send_mode": "auto_send", "language_hint": "en"},
    )
    assert auto.status_code == 200
    auto_body = auto.json()
    assert auto_body["send_mode"] == "auto_send"
    assert auto_body["job_id"] == "job_fake_voice_auto_send"
    assert len(fake_runtime.calls) == 1
    thread = store.get_chat_thread_for_session(session.id)
    assert thread is not None
    messages = store.list_chat_messages(thread.id)
    assert any(m.role == "user" and m.source_kind == "voice_command" for m in messages)
    assert any(m.role == "assistant" and m.status == "queued" for m in messages)
    assert seeded.revision.id is not None


def test_voice_command_empty_transcription_is_flagged(
    store: SQLiteStore, app_settings: AppSettings, monkeypatch: pytest.MonkeyPatch
):
    # A VAD false-trigger on silence/noise yields empty STT text; the response must
    # flag it (transcription_empty) so the hands-free loop skips it instead of sending
    # the human-facing placeholder to the model.
    session = store.create_session(title="Voice", source_kind="upload")
    _seed_transcript(store, session.id)
    app = _make_test_app(
        store=store,
        settings=app_settings,
        include_voice_commands=True,
        job_runtime=FakeJobRuntime(),
    )
    client = TestClient(app)

    monkeypatch.setattr(
        voice_commands_router,
        "_audio_service_from_runtime",
        lambda settings, runtime_info: FakeVoiceAudioStorageService(
            settings=settings, session_id=session.id
        ),
    )
    monkeypatch.setattr(
        voice_commands_router,
        "FasterWhisperSttClient",
        lambda: FakeCommandSttClient("   "),  # whitespace-only -> empty after strip
    )

    resp = client.post(
        f"/api/v1/sessions/{session.id}/voice-commands",
        files={"audio_file": ("cmd.wav", io.BytesIO(b"RIFFfake"), "audio/wav")},
        data={"send_mode": "review_then_send", "language_hint": "de"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcription_empty"] is True
    assert "please edit before sending" in body["transcribed_text"]
    assert body["job_id"] is None


def test_chat_reply_regression_persists_citations_and_action_proposals(
    store: SQLiteStore, app_settings: AppSettings
):
    session = store.create_session(title="Chat regression", source_kind="upload")
    seeded = _seed_transcript(
        store,
        session.id,
        texts=[
            "Discussed next steps for customer follow-up email.",
            "Need a task list for owners and deadlines.",
            "Summarize notes in a document.",
        ],
    )
    thread, user, assistant = _seed_chat_thread_with_assistant(
        store, session.id, seeded.revision.id
    )
    retriever = TranscriptRetriever(store, app_settings)
    orchestrator = ChatOrchestrator(store=store, settings=app_settings, retriever=retriever)

    result = orchestrator.run_chat_reply_job(
        ChatReplyJobInput(
            session_id=session.id,
            thread_id=thread.id,
            user_message_id=user.id,
            assistant_message_id=assistant.id,
            transcript_revision_id=seeded.revision.id,
        )
    )
    assert result.citation_count >= 1
    assert result.model_name

    assistant_refreshed = store.get_chat_message(assistant.id)
    assert assistant_refreshed is not None
    assert assistant_refreshed.status == "completed"
    assert store.list_message_citations(assistant.id)
    actions = store.list_action_proposals_for_message(assistant.id)
    assert actions
    assert {item.action_type for item in actions}.intersection({"email_draft", "task_draft"})


class _FakeStreamingEngine:
    """Records synthesis calls and returns deterministic PCM (no real TTS needed)."""

    name = "fake"
    voice = "fake-voice"
    sample_rate = 22050

    def __init__(self, language: str = "de") -> None:
        self.calls: list[str] = []
        self.language = language

    def synthesize_pcm(self, text: str) -> bytes:
        self.calls.append(text)
        return b"\x00\x01" * 8  # 16 bytes of dummy PCM


class _FakeStreamingChatClient:
    model_label = "fake-llm"

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    def generate_stream(self, request):  # noqa: ANN001
        yield from self._tokens


def test_voice_turn_streams_sentences_and_persists(store: SQLiteStore, app_settings: AppSettings):
    session = store.create_session(title="Voice turn", source_kind="upload")
    seeded = _seed_transcript(
        store,
        session.id,
        texts=["Wir starten das Projekt heute.", "Naechste Schritte folgen bald."],
    )
    thread = store.get_or_create_chat_thread(session_id=session.id)
    user = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=seeded.revision.id,
        role="user",
        content_markdown="Was ist der Plan?",
        content_plain_text="Was ist der Plan?",
        source_kind="voice_command",
        status="completed",
    )
    assistant = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=seeded.revision.id,
        role="assistant",
        content_markdown="",
        content_plain_text="",
        source_kind="assistant_reply",
        status="running",
        metadata={"pending": True},
    )

    engine = _FakeStreamingEngine()
    client = _FakeStreamingChatClient(["Hallo Team. ", "Wir senden eine E-Mail."])
    retriever = TranscriptRetriever(store, app_settings)
    orchestrator = ChatOrchestrator(
        store=store, settings=app_settings, retriever=retriever, model_client=client
    )

    events = list(
        orchestrator.stream_voice_turn(
            session_id=session.id,
            thread_id=thread.id,
            user_message_id=user.id,
            assistant_message_id=assistant.id,
            engine=engine,
            transcript_revision_id=seeded.revision.id,
        )
    )

    sentences = [e for e in events if e.kind == "sentence"]
    done = [e for e in events if e.kind == "done"]
    assert [e.text for e in sentences] == ["Hallo Team.", "Wir senden eine E-Mail."]
    assert all(e.pcm for e in sentences)
    # Engine is called once per spoken sentence (markers/markdown stripped).
    assert engine.calls == ["Hallo Team.", "Wir senden eine E-Mail."]
    assert len(done) == 1
    assert done[0].model_name == "fake-llm"

    refreshed = store.get_chat_message(assistant.id)
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert "Hallo Team" in refreshed.content_markdown


class _FailingStreamingChatClient:
    model_label = "fake-llm"

    def generate_stream(self, request):  # noqa: ANN001
        raise RuntimeError("ollama unavailable")
        yield  # pragma: no cover - makes this a generator function


def test_voice_turn_falls_back_to_spoken_reply_when_stream_fails(
    store: SQLiteStore, app_settings: AppSettings
):
    # The producer thread captures the streaming error; the consumer must still emit a
    # single spoken rule-based reply (and a done) rather than hang or go silent.
    session = store.create_session(title="Voice turn", source_kind="upload")
    seeded = _seed_transcript(store, session.id, texts=["Wir starten das Projekt heute."])
    thread = store.get_or_create_chat_thread(session_id=session.id)
    user = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=seeded.revision.id,
        role="user",
        content_markdown="Was ist der Plan?",
        content_plain_text="Was ist der Plan?",
        source_kind="voice_command",
        status="completed",
    )
    assistant = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=seeded.revision.id,
        role="assistant",
        content_markdown="",
        content_plain_text="",
        source_kind="assistant_reply",
        status="running",
        metadata={"pending": True},
    )

    engine = _FakeStreamingEngine()
    orchestrator = ChatOrchestrator(
        store=store,
        settings=app_settings,
        retriever=TranscriptRetriever(store, app_settings),
        model_client=_FailingStreamingChatClient(),
    )

    events = list(
        orchestrator.stream_voice_turn(
            session_id=session.id,
            thread_id=thread.id,
            user_message_id=user.id,
            assistant_message_id=assistant.id,
            engine=engine,
            transcript_revision_id=seeded.revision.id,
        )
    )

    sentences = [e for e in events if e.kind == "sentence"]
    done = [e for e in events if e.kind == "done"]
    assert len(sentences) >= 1  # spoken fallback was produced
    assert len(done) == 1
    refreshed = store.get_chat_message(assistant.id)
    assert refreshed is not None
    assert refreshed.status == "completed"


def test_voice_turn_yields_plain_text_even_when_model_emits_markdown(
    store: SQLiteStore, app_settings: AppSettings
):
    session = store.create_session(title="Markdown voice", source_kind="upload")
    thread = store.get_or_create_chat_thread(session_id=session.id)
    user = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=None,
        role="user",
        content_markdown="Nenne die Schritte.",
        content_plain_text="Nenne die Schritte.",
        source_kind="voice_command",
        status="completed",
    )
    assistant = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=None,
        role="assistant",
        content_markdown="",
        content_plain_text="",
        source_kind="assistant_reply",
        status="running",
        metadata={"pending": True},
    )
    engine = _FakeStreamingEngine()
    # The model disobeys the no-markdown instruction and emits a heading + bullet list
    # (each bullet on its own line, as real markdown is formatted).
    client = _FakeStreamingChatClient(["## Schritte\n\n", "- Erstens dies.\n", "- Zweitens das.\n"])
    retriever = TranscriptRetriever(store, app_settings)
    orchestrator = ChatOrchestrator(
        store=store, settings=app_settings, retriever=retriever, model_client=client
    )

    events = list(
        orchestrator.stream_voice_turn(
            session_id=session.id,
            thread_id=thread.id,
            user_message_id=user.id,
            assistant_message_id=assistant.id,
            engine=engine,
        )
    )

    # Spoken frames and the audio that was synthesized must contain no markdown syntax.
    for e in (e for e in events if e.kind == "sentence"):
        for token in ("#", "*", "- ", "|"):
            assert token not in e.text
    for spoken in engine.calls:
        for token in ("#", "*", "- ", "|"):
            assert token not in spoken

    # The persisted message is plain text too — no leftover markdown in the bubble.
    refreshed = store.get_chat_message(assistant.id)
    assert refreshed is not None
    for token in ("##", "- ", "*"):
        assert token not in refreshed.content_markdown
    assert "Erstens dies." in refreshed.content_markdown


def test_voice_turn_drops_citation_footnotes_but_keeps_records(
    store: SQLiteStore, app_settings: AppSettings
):
    session = store.create_session(title="Voice citations", source_kind="upload")
    seeded = _seed_transcript(store, session.id, texts=["Wir starten das Projekt heute."])
    retriever = TranscriptRetriever(store, app_settings)
    retriever.index_revision(seeded.revision)
    query = "Was ist der Plan?"
    hits = retriever.retrieve(
        revision=seeded.revision, query=query, top_k=12, include_neighbors=True
    )
    assert hits  # retrieval found the seeded segment to cite
    seg_id = hits[0].chunk.segment_id

    thread = store.get_or_create_chat_thread(session_id=session.id)
    user = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=seeded.revision.id,
        role="user",
        content_markdown=query,
        content_plain_text=query,
        source_kind="voice_command",
        status="completed",
    )
    assistant = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=seeded.revision.id,
        role="assistant",
        content_markdown="",
        content_plain_text="",
        source_kind="assistant_reply",
        status="running",
        metadata={"pending": True},
    )
    engine = _FakeStreamingEngine()
    client = _FakeStreamingChatClient([f"Der Plan steht fest. [SEG:{seg_id}]"])
    orchestrator = ChatOrchestrator(
        store=store, settings=app_settings, retriever=retriever, model_client=client
    )

    list(
        orchestrator.stream_voice_turn(
            session_id=session.id,
            thread_id=thread.id,
            user_message_id=user.id,
            assistant_message_id=assistant.id,
            engine=engine,
        )
    )

    refreshed = store.get_chat_message(assistant.id)
    assert refreshed is not None
    # No inline footnote text and no leftover [SEG:] marker in the spoken/persisted answer.
    assert "[SEG:" not in refreshed.content_markdown
    assert "[1]" not in refreshed.content_markdown
    assert "Der Plan steht fest." in refreshed.content_markdown
    # The structured citation record is still kept (only the footnote text is dropped).
    assert len(store.list_message_citations(assistant.id)) == 1


class _FakeChatClient:
    def generate(self, request):
        from backend.app.services.chat_orchestrator import ChatModelResponse

        return ChatModelResponse(content_markdown="Mir geht es gut, danke!", model_name="fake")


def test_chat_reply_without_transcript_is_general(store: SQLiteStore, app_settings: AppSettings):
    session = store.create_session(title="No transcript", source_kind="upload")
    thread = store.get_or_create_chat_thread(session_id=session.id)
    user = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=None,
        role="user",
        content_markdown="Hallo, wie geht es dir?",
        content_plain_text="Hallo, wie geht es dir?",
        source_kind="typed",
        status="completed",
    )
    assistant = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=None,
        role="assistant",
        content_markdown="",
        content_plain_text="",
        source_kind="assistant_reply",
        status="queued",
        metadata={"pending": True},
    )
    retriever = TranscriptRetriever(store, app_settings)
    orchestrator = ChatOrchestrator(
        store=store, settings=app_settings, retriever=retriever, model_client=_FakeChatClient()
    )

    result = orchestrator.run_chat_reply_job(
        ChatReplyJobInput(
            session_id=session.id,
            thread_id=thread.id,
            user_message_id=user.id,
            assistant_message_id=assistant.id,
            transcript_revision_id=None,
        )
    )
    assert result.transcript_revision_id == ""  # no transcript
    assert result.retrieval_hit_count == 0
    refreshed = store.get_chat_message(assistant.id)
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert "gut" in refreshed.content_markdown.lower()
    assert store.list_message_citations(assistant.id) == []


def test_voice_turn_without_transcript_uses_engine_language(
    store: SQLiteStore, app_settings: AppSettings
):
    session = store.create_session(title="No transcript voice", source_kind="upload")
    thread = store.get_or_create_chat_thread(session_id=session.id)
    user = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=None,
        role="user",
        content_markdown="What is two plus two?",
        content_plain_text="What is two plus two?",
        source_kind="voice_command",
        status="completed",
    )
    assistant = store.create_chat_message(
        thread_id=thread.id,
        session_id=session.id,
        transcript_revision_id=None,
        role="assistant",
        content_markdown="",
        content_plain_text="",
        source_kind="assistant_reply",
        status="running",
        metadata={"pending": True},
    )
    engine = _FakeStreamingEngine(language="en")
    client = _FakeStreamingChatClient(["Two plus two is four."])
    retriever = TranscriptRetriever(store, app_settings)
    orchestrator = ChatOrchestrator(
        store=store, settings=app_settings, retriever=retriever, model_client=client
    )

    events = list(
        orchestrator.stream_voice_turn(
            session_id=session.id,
            thread_id=thread.id,
            user_message_id=user.id,
            assistant_message_id=assistant.id,
            engine=engine,
        )
    )
    assert [e for e in events if e.kind == "sentence"]  # spoke without a transcript
    refreshed = store.get_chat_message(assistant.id)
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert "four" in refreshed.content_markdown.lower()
    assert store.list_message_citations(assistant.id) == []
