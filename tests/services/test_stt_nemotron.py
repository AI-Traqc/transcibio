import base64
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from backend.app.services.stt_nemotron import (
    MAX_AUDIO_MS,
    PLAIN_PROMPT,
    SPEAKER_PROMPT,
    STATUS_STALE_SECONDS,
    NemotronConfig,
    NemotronError,
    NemotronTranscriptionEngine,
    build_request_body,
    check_nemotron_server,
    nemotron_status_file,
    parse_response,
)


def _closed_local_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeTransport:
    """Records requests; returns a preset response or raises."""

    def __init__(self, response=None, *, should_fail: bool = False) -> None:
        self.response = response or {}
        self.should_fail = should_fail
        self.calls: list[tuple[str, dict, float]] = []

    def __call__(self, url: str, body: dict, timeout: float) -> dict:
        self.calls.append((url, body, timeout))
        if self.should_fail:
            raise NemotronError("Nemotron server not reachable (fake)")
        return self.response


def _engine(transport, **config) -> NemotronTranscriptionEngine:
    cfg = NemotronConfig(
        url=config.get("url", "http://127.0.0.1:8010/v1/chat/completions"),
        model="nvidia/test-model",
        timeout_seconds=5.0,
    )
    return NemotronTranscriptionEngine(
        config=cfg, transport=transport, audio_encoder=lambda path: b"fLaC-bytes"
    )


def test_request_body_matches_model_card_fields():
    body = build_request_body(model="m", audio_flac=b"abc", with_speakers=True)
    content = body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": SPEAKER_PROMPT}
    assert content[1]["audio_url"]["url"] == "data:audio/flac;base64," + base64.b64encode(
        b"abc"
    ).decode("ascii")
    # extra_body fields are top-level in a raw request
    assert body["temperature"] == 0
    assert body["skip_special_tokens"] is False
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["mm_processor_kwargs"] == {"capture_ctc_timestamps": True}


def test_plain_prompt_when_diarization_is_off():
    body = build_request_body(model="m", audio_flac=b"abc", with_speakers=False)
    assert body["messages"][0]["content"][0]["text"] == PLAIN_PROMPT


def test_rejects_audio_over_one_hour_without_calling_the_server(tmp_path: Path):
    transport = FakeTransport()
    with pytest.raises(NemotronError, match="60 min"):
        _engine(transport).transcribe(
            tmp_path / "long.wav",
            language_hint="de",
            preset="balanced",
            diarization_enabled=True,
            duration_ms=MAX_AUDIO_MS + 1,
        )
    assert transport.calls == []


def test_server_down_fails_with_clear_message_and_no_fallback(tmp_path: Path):
    url = f"http://127.0.0.1:{_closed_local_port()}/v1/chat/completions"
    engine = NemotronTranscriptionEngine(
        config=NemotronConfig(url=url, model="m", timeout_seconds=2.0),
        audio_encoder=lambda path: b"fLaC",
    )
    with pytest.raises(NemotronError, match="not reachable"):
        engine.transcribe(
            tmp_path / "a.wav",
            language_hint="de",
            preset="balanced",
            diarization_enabled=True,
            duration_ms=1000,
        )


def test_models_url_derived_from_chat_url():
    cfg = NemotronConfig(
        url="http://nemotron:8010/v1/chat/completions", model="m", timeout_seconds=1.0
    )
    assert cfg.models_url == "http://nemotron:8010/v1/models"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("TRANSCIBIO_NEMOTRON_URL", "http://h:1/v1/chat/completions")
    monkeypatch.setenv("TRANSCIBIO_NEMOTRON_MODEL", "x/y")
    monkeypatch.setenv("TRANSCIBIO_NEMOTRON_TIMEOUT_SECONDS", "42")
    cfg = NemotronConfig.from_env()
    assert (cfg.url, cfg.model, cfg.timeout_seconds) == (
        "http://h:1/v1/chat/completions",
        "x/y",
        42.0,
    )


# --- Parsing a real server response (tests/fixtures/nemotron) ---

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nemotron" / "transcribe_response.json"


def _fixture() -> dict:
    import json

    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _store(tmp_path: Path):
    from backend.app.store import SQLiteStore

    store = SQLiteStore(tmp_path / "t.db")
    store.initialize()
    return store


def test_fixture_becomes_speaker_turns_through_assembly(tmp_path: Path):
    from backend.app.services.transcript_assembly import TranscriptAssemblyService

    stt, diarization = _engine(FakeTransport(_fixture())).transcribe(
        tmp_path / "a.wav",
        language_hint="de",
        preset="balanced",
        diarization_enabled=True,
        duration_ms=264_000,
    )
    assert diarization.used is True and diarization.provider == "nemotron"
    assert stt.model_name == "nvidia/test-model" and stt.detected_language == "de"

    store = _store(tmp_path)
    session = store.create_session(title="t", source_kind="upload")
    result = TranscriptAssemblyService(store).persist_initial_revision(
        session_id=session.id, stt_result=stt, diarization=diarization
    )
    assert result.speaker_count == 2
    segments = store.list_transcript_segments(result.revision_id)
    key_by_id = {s.id: s.speaker_key for s in store.list_transcript_speakers(result.revision_id)}
    keys = [key_by_id[seg.speaker_id] for seg in segments]
    # Turns alternate between the two speakers, as tagged by <spk:0>/<spk:1>.
    assert keys[:4] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00", "SPEAKER_01"]
    assert segments[0].text.startswith("Schmidt Sanitär und Heizung")
    assert segments[1].text.startswith("Ja, guten Tag")
    assert segments[0].start_ms == 0 and segments[1].start_ms > segments[0].end_ms - 1


def test_words_keep_punctuation_for_the_sentence_split():
    stt, _ = parse_response(_fixture(), model_name="m", preset="balanced", with_speakers=True)
    texts = [w.text for seg in stt.segments for w in seg.words]
    assert "Heizung," in texts and any(t.endswith(".") for t in texts)


def test_without_speakers_returns_unused_diarization():
    stt, diarization = parse_response(
        _fixture(), model_name="m", preset="balanced", with_speakers=False
    )
    assert diarization.used is False and diarization.segments == ()
    assert len(stt.segments) == 1  # one speaker -> one run of words


def test_alignment_error_fails_clearly():
    data = _fixture()
    data["ctc_timestamps"]["error"] = "alignment failed"
    with pytest.raises(NemotronError, match="alignment failed"):
        parse_response(data, model_name="m", preset="balanced", with_speakers=True)


def test_missing_timestamps_fails_clearly():
    data = _fixture()
    del data["ctc_timestamps"]
    with pytest.raises(NemotronError, match="timestamps"):
        parse_response(data, model_name="m", preset="balanced", with_speakers=True)


# --- Voice input (voice commands / voice mode) through Nemotron ---


def test_voice_input_returns_plain_text_without_speaker_tags(tmp_path: Path):
    transport = FakeTransport(_fixture())
    text, model = _engine(transport).transcribe_text(tmp_path / "cmd.wav")
    assert text.startswith("Schmidt Sanitär und Heizung")
    assert "<spk:" not in text
    assert model == "nvidia/test-model"
    body = transport.calls[0][1]
    assert body["messages"][0]["content"][0]["text"] == PLAIN_PROMPT
    assert "mm_processor_kwargs" not in body  # no word alignment for short clips


def test_voice_input_server_down_raises_instead_of_falling_back(tmp_path: Path):
    with pytest.raises(NemotronError):
        _engine(FakeTransport(should_fail=True)).transcribe_text(tmp_path / "cmd.wav")


# --- Server status (Settings) ---------------------------------------------------------


class _ModelsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        body = json.dumps({"data": [{"id": "served/model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def running_server_url():
    server = HTTPServer(("127.0.0.1", 0), _ModelsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
    server.shutdown()
    server.server_close()


def _down_config() -> NemotronConfig:
    url = f"http://127.0.0.1:{_closed_local_port()}/v1/chat/completions"
    return NemotronConfig(url=url, model="m", timeout_seconds=1.0)


def _write_heartbeat(path: Path, *, started_at: float, written_at: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"started_at": started_at}), encoding="utf-8")
    os.utime(path, (written_at, written_at))
    return path


def test_status_file_lives_in_the_mounted_model_folder(tmp_path: Path):
    path = nemotron_status_file(tmp_path)
    assert path == tmp_path / "models" / "nemotron" / ".server-status.json"


def test_status_running_when_server_answers(running_server_url, tmp_path: Path):
    config = NemotronConfig(url=running_server_url, model="m", timeout_seconds=1.0)
    # A heartbeat is still written while vLLM runs; the answering server wins.
    status_file = _write_heartbeat(tmp_path / "s.json", started_at=1000.0, written_at=1300.0)
    status = check_nemotron_server(config, status_file=status_file, now=lambda: 1300.0)
    assert status["state"] == "running"
    assert status["reachable"] is True
    assert status["served_models"] == ["served/model"]


def test_status_starting_while_heartbeat_is_fresh_and_port_closed(tmp_path: Path):
    status_file = _write_heartbeat(tmp_path / "s.json", started_at=1000.0, written_at=1123.0)
    status = check_nemotron_server(_down_config(), status_file=status_file, now=lambda: 1125.0)
    assert status["state"] == "starting"
    assert status["starting_seconds"] == 125
    assert status["reachable"] is False


def test_status_stopped_when_heartbeat_is_stale(tmp_path: Path):
    written_at = 1000.0
    status_file = _write_heartbeat(tmp_path / "s.json", started_at=900.0, written_at=written_at)
    status = check_nemotron_server(
        _down_config(),
        status_file=status_file,
        now=lambda: written_at + STATUS_STALE_SECONDS + 1,
    )
    assert status["state"] == "stopped"
    assert "starting_seconds" not in status


def test_status_stopped_without_heartbeat(tmp_path: Path):
    status = check_nemotron_server(_down_config(), status_file=tmp_path / "missing.json")
    assert status["state"] == "stopped"
    assert check_nemotron_server(_down_config())["state"] == "stopped"


def test_status_stopped_when_heartbeat_is_unreadable(tmp_path: Path):
    status_file = tmp_path / "s.json"
    status_file.write_text("not json", encoding="utf-8")
    status = check_nemotron_server(_down_config(), status_file=status_file)
    assert status["state"] == "stopped"
