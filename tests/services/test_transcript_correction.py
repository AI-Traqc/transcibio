from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.services.transcript_correction as correction_module
from backend.app.config import AppSettings
from backend.app.services.transcript_correction import (
    TranscriptCorrectionService,
    _parse_json_object_text,
    _parse_ollama_correction_response,
    _post_ollama_json,
    _resolve_ollama_chat_url,
    _resolve_ollama_correction_timeout_seconds,
)
from backend.app.store import TranscriptSegmentRecord


def make_settings(*, llm_provider: str = "ollama") -> AppSettings:
    root = Path.cwd()
    return AppSettings(
        app_name="Transcibio API",
        environment="test",
        host="127.0.0.1",
        port=8000,
        data_root=root / "data",
        db_path=root / "data" / "privata.db",
        sessions_root=root / "data" / "sessions",
        processing_profile="balanced",
        stt_provider="faster-whisper",
        llm_provider=llm_provider,
        tts_provider="piper",
        ffmpeg_required=False,
    )


def make_segment(*, segment_id: str = "seg-1", text: str = "helo world") -> TranscriptSegmentRecord:
    return TranscriptSegmentRecord(
        id=segment_id,
        revision_id="rev-1",
        segment_index=1,
        speaker_id=None,
        start_ms=0,
        end_ms=1000,
        text=text,
        confidence=0.9,
        word_count=2,
        embedding_vector_ref=None,
    )


def test_try_llm_correction_uses_ollama_model_from_effective_settings(monkeypatch):
    store = SimpleNamespace(
        get_app_setting=lambda key: {"chat": {"llm_provider": "ollama", "model_name": "qwen2.5:7b"}}
    )
    service = TranscriptCorrectionService(
        store=store, settings=make_settings(llm_provider="lmstudio")
    )
    segment = make_segment()
    captured: dict[str, str] = {}

    def fake_run(segments, *, model_name: str):
        captured["model_name"] = model_name
        return {segments[0].id: "Hello world"}

    monkeypatch.setattr(service, "_run_ollama_correction", fake_run)

    corrected, model_name, warning = service._try_llm_correction([segment])

    assert corrected == {segment.id: "Hello world"}
    assert model_name == "qwen2.5:7b"
    assert warning is None
    assert captured["model_name"] == "qwen2.5:7b"


def test_try_llm_correction_falls_back_when_ollama_request_fails(monkeypatch):
    store = SimpleNamespace(
        get_app_setting=lambda key: {
            "chat": {"llm_provider": "ollama", "model_name": "gpt-oss-20b"}
        }
    )
    service = TranscriptCorrectionService(store=store, settings=make_settings())
    segment = make_segment()

    def fake_run(segments, *, model_name: str):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(service, "_run_ollama_correction", fake_run)

    corrected, model_name, warning = service._try_llm_correction([segment])

    assert corrected is None
    assert model_name == "gpt-oss-20b"
    assert warning == "Ollama correction failed: connection refused; using rules fallback."


def test_parse_ollama_correction_response_requires_all_segments():
    response_payload = {
        "message": {"content": '{"segments":[{"segment_id":"seg-1","text":"Hello world"}]}'}
    }
    segments = [make_segment(segment_id="seg-1"), make_segment(segment_id="seg-2", text="by world")]

    with pytest.raises(RuntimeError, match="omitted one or more transcript segments"):
        _parse_ollama_correction_response(response_payload, segments)


def test_parse_json_object_text_accepts_fenced_json():
    raw = '```json\n{"segments":[{"segment_id":"seg-1","text":"Hello world"}]}\n```'

    parsed = _parse_json_object_text(raw)

    assert parsed == {"segments": [{"segment_id": "seg-1", "text": "Hello world"}]}


def test_parse_json_object_text_accepts_embedded_json():
    raw = (
        'Here is the corrected payload:\n{"segments":[{"segment_id":"seg-1","text":"Hello world"}]}'
    )

    parsed = _parse_json_object_text(raw)

    assert parsed == {"segments": [{"segment_id": "seg-1", "text": "Hello world"}]}


def test_resolve_ollama_chat_url_prefers_explicit_chat_url(monkeypatch):
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_CHAT_URL", "http://127.0.0.1:11434/api/chat")
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_GENERATE_URL", "http://127.0.0.1:11434/api/generate")

    resolved = _resolve_ollama_chat_url()

    assert resolved == "http://127.0.0.1:11434/api/chat"


def test_resolve_ollama_chat_url_derives_from_generate_url(monkeypatch):
    monkeypatch.delenv("TRANSCIBIO_OLLAMA_CHAT_URL", raising=False)
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_GENERATE_URL", "http://127.0.0.1:11434/api/generate")

    resolved = _resolve_ollama_chat_url()

    assert resolved == "http://127.0.0.1:11434/api/chat"


def test_resolve_ollama_correction_timeout_seconds_uses_default_for_invalid_env(monkeypatch):
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_CORRECTION_TIMEOUT_SECONDS", "invalid")

    resolved = _resolve_ollama_correction_timeout_seconds()

    assert resolved == 180.0


def test_resolve_ollama_correction_timeout_seconds_uses_env_value(monkeypatch):
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_CORRECTION_TIMEOUT_SECONDS", "240")

    resolved = _resolve_ollama_correction_timeout_seconds()

    assert resolved == 240.0


def test_run_ollama_correction_uses_chat_payload(monkeypatch):
    service = TranscriptCorrectionService(
        store=SimpleNamespace(get_app_setting=lambda key: {}),
        settings=make_settings(),
    )
    segment = make_segment()
    captured: dict[str, object] = {}

    def fake_post(
        url: str, payload: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        return {
            "message": {"content": '{"segments":[{"segment_id":"seg-1","text":"Hello world"}]}'}
        }

    monkeypatch.setattr(correction_module, "_post_ollama_json", fake_post)
    monkeypatch.delenv("TRANSCIBIO_OLLAMA_CHAT_URL", raising=False)
    monkeypatch.delenv("TRANSCIBIO_OLLAMA_GENERATE_URL", raising=False)
    monkeypatch.delenv("TRANSCIBIO_OLLAMA_CORRECTION_TIMEOUT_SECONDS", raising=False)

    corrected = service._run_ollama_correction([segment], model_name="gpt-oss:20b")

    assert corrected == {"seg-1": "Hello world"}
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["timeout_seconds"] == 180.0
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "gpt-oss:20b"
    assert payload["stream"] is False
    assert isinstance(payload["messages"], list)
    assert isinstance(payload["format"], dict)


def test_post_ollama_json_surfaces_timeout_seconds(monkeypatch):
    def fake_urlopen(request, timeout):
        raise correction_module.socket.timeout("timed out")

    monkeypatch.setattr(correction_module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="timed out after 123s"):
        _post_ollama_json(
            "http://127.0.0.1:11434/api/chat",
            {"model": "gpt-oss:20b"},
            timeout_seconds=123.0,
        )
