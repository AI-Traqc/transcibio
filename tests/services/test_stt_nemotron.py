import base64
import socket
from pathlib import Path

import pytest

from backend.app.services.stt_nemotron import (
    MAX_AUDIO_MS,
    PLAIN_PROMPT,
    SPEAKER_PROMPT,
    NemotronConfig,
    NemotronError,
    NemotronTranscriptionEngine,
    build_request_body,
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
