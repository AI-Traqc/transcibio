import pytest

from backend.app.services.chat_orchestrator import (
    ChatModelRequest,
    LmStudioChatModelClient,
    LocalChatHttpError,
    OllamaChatModelClient,
    RuleBasedChatModelClient,
)

_REQUEST = ChatModelRequest(
    user_message="Fasse das Meeting zusammen.",
    transcript_context="- [00:00-00:05] (Anna) [SEG:a1] Wir starten das Projekt.",
    response_language="de",
)

_VOICE_REQUEST = ChatModelRequest(
    user_message="Fasse das Meeting zusammen.",
    transcript_context="- [00:00-00:05] (Anna) [SEG:a1] Wir starten das Projekt.",
    response_language="de",
    for_speech=True,
)


def test_ollama_stream_parses_ndjson_and_stops_on_done(monkeypatch):
    client = OllamaChatModelClient(model_name="test-model")
    lines = [
        '{"response": "Hallo ", "done": false}',
        '{"response": "Welt.", "done": false}',
        '{"response": "", "done": true}',
        '{"response": "ignored after done"}',
    ]
    monkeypatch.setattr(client, "_iter_lines", lambda payload, **kw: iter(lines))

    assert "".join(client.generate_stream(_REQUEST)) == "Hallo Welt."


def test_lmstudio_stream_parses_sse_deltas_and_stops_on_done(monkeypatch):
    client = LmStudioChatModelClient()
    lines = [
        'data: {"choices": [{"delta": {"content": "Guten "}}]}',
        ": keepalive comment",
        'data: {"choices": [{"delta": {"content": "Tag."}}]}',
        "data: [DONE]",
        'data: {"choices": [{"delta": {"content": "after done"}}]}',
    ]
    monkeypatch.setattr(client, "_iter_lines", lambda payload, **kw: iter(lines))

    assert "".join(client.generate_stream(_REQUEST)) == "Guten Tag."


def test_ollama_stream_sets_stream_flag_true(monkeypatch):
    client = OllamaChatModelClient(model_name="test-model")
    captured: dict = {}

    def fake_iter(payload, **kw):
        captured.update(payload)
        return iter(['{"response": "x", "done": true}'])

    monkeypatch.setattr(client, "_iter_lines", fake_iter)
    list(client.generate_stream(_REQUEST))

    assert captured["stream"] is True
    assert captured["model"] == "test-model"


def test_rule_based_stream_yields_full_answer_once():
    client = RuleBasedChatModelClient()
    chunks = list(client.generate_stream(_REQUEST))
    assert len(chunks) == 1
    assert chunks[0] == client.generate(_REQUEST).content_markdown


def test_ollama_voice_turn_disables_thinking(monkeypatch):
    # Reasoning models burn the token budget on chain-of-thought before emitting any
    # answer, producing a silent voice turn; voice requests must disable thinking.
    client = OllamaChatModelClient(model_name="test-model")
    captured: dict = {}

    def fake_iter(payload, **kw):
        captured.update(payload)
        return iter(['{"response": "Hallo.", "done": true}'])

    monkeypatch.setattr(client, "_iter_lines", fake_iter)
    list(client.generate_stream(_VOICE_REQUEST))

    assert captured["think"] is False


def test_ollama_typed_chat_omits_think(monkeypatch):
    client = OllamaChatModelClient(model_name="test-model")
    captured: dict = {}

    def fake_iter(payload, **kw):
        captured.update(payload)
        return iter(['{"response": "Hallo.", "done": true}'])

    monkeypatch.setattr(client, "_iter_lines", fake_iter)
    list(client.generate_stream(_REQUEST))

    assert "think" not in captured


def test_ollama_voice_retries_without_think_when_model_rejects_it(monkeypatch):
    # A model that does not support the `think` field returns HTTP 400; the voice path
    # retries once without it so older/non-reasoning models keep working.
    client = OllamaChatModelClient(model_name="test-model")
    payloads: list[dict] = []

    def fake_iter(payload, **kw):
        payloads.append(dict(payload))
        if "think" in payload:
            raise LocalChatHttpError("Ollama", 400, "model does not support thinking")
        return iter(['{"response": "Hallo Welt.", "done": true}'])

    monkeypatch.setattr(client, "_iter_lines", fake_iter)
    out = "".join(client.generate_stream(_VOICE_REQUEST))

    assert out == "Hallo Welt."
    assert len(payloads) == 2
    assert payloads[0]["think"] is False
    assert "think" not in payloads[1]


def test_ollama_voice_does_not_retry_on_unrelated_http_error(monkeypatch):
    client = OllamaChatModelClient(model_name="test-model")
    calls = {"n": 0}

    def fake_iter(payload, **kw):
        calls["n"] += 1
        raise LocalChatHttpError("Ollama", 500, "internal server error")

    monkeypatch.setattr(client, "_iter_lines", fake_iter)
    with pytest.raises(LocalChatHttpError):
        list(client.generate_stream(_VOICE_REQUEST))

    assert calls["n"] == 1  # a 500 is not a thinking-unsupported error -> no retry
