from backend.app.services.chat_orchestrator import (
    _PROMPT_AND_ANSWER_RESERVE_TOKENS,
    _RETRIEVAL_CONTEXT_TOKENS,
    ChatModelRequest,
    ChatOrchestrator,
    OllamaChatModelClient,
    _build_user_content,
    _estimated_context_tokens,
    _full_transcript_context_tokens,
    _system_instruction,
    _within_token_budget,
)
from backend.app.services.retrieval import RetrievalChunk, RetrievalHit


def _req(
    msg: str = "Hallo", ctx: str = "", lang: str = "de", for_speech: bool = False
) -> ChatModelRequest:
    return ChatModelRequest(
        user_message=msg,
        transcript_context=ctx,
        response_language=lang,
        for_speech=for_speech,
    )


def test_system_instruction_is_general_when_no_context():
    instruction = _system_instruction(_req(ctx=""))
    assert "transcript" not in instruction.lower()
    assert "Antworte auf Deutsch" in instruction


def test_system_instruction_blends_when_context_present():
    instruction = _system_instruction(_req(ctx="- [S1] 00:00–00:05, Anna: etwas"))
    assert "transcript" in instruction.lower()
    assert "[S3]" in instruction
    # Blend, not strict: explicitly allows general knowledge when uncovered.
    assert "general knowledge" in instruction.lower()


def test_system_instruction_respects_english():
    assert "Respond in en" in _system_instruction(_req(lang="en"))


def test_speech_instruction_forbids_markdown_english():
    instruction = _system_instruction(_req(lang="en", for_speech=True))
    lowered = instruction.lower()
    # Voice replies are read aloud: no markdown, and never the typed-chat directive.
    assert "Answer in markdown." not in instruction
    assert "markdown" in lowered  # it explicitly forbids it
    assert "bullet" in lowered
    assert "read aloud" in lowered


def test_speech_instruction_forbids_markdown_german():
    instruction = _system_instruction(_req(lang="de", for_speech=True))
    # German voice prompt forbids markdown in German.
    assert "Answer in markdown." not in instruction
    assert "kein Markdown" in instruction
    assert "Aufzählungspunkte" in instruction  # bullet points
    assert "vorgelesen" in instruction  # read aloud


def test_speech_instruction_locks_language_to_german():
    instruction = _system_instruction(_req(lang="de", for_speech=True))
    # Hard lock so the model cannot drift into a language Piper cannot pronounce.
    assert "ausschließlich auf Deutsch" in instruction
    assert "andere" in instruction.lower()  # "even if the user speaks another language"


def test_speech_instruction_german_is_fully_german_and_repeats_lock():
    instruction = _system_instruction(_req(lang="de", for_speech=True))
    # The whole prompt is German (no leftover English instruction text), so a small
    # local model isn't pulled toward English by a mostly-English prompt.
    assert "voice assistant" not in instruction.lower()
    assert "Sprachassistent" in instruction
    # The language lock is repeated as the final instruction (strongest position).
    assert instruction.rstrip().endswith("auf Deutsch.")
    assert instruction.count("ausschließlich auf Deutsch") == 2


def test_german_voice_prompt_text_adds_priming_cue():
    from backend.app.services.chat_orchestrator import _build_prompt_text

    prompt = _build_prompt_text(_req(lang="de", for_speech=True))
    # Ollama /api/generate loses role separation; a German answer cue biases the
    # first generated token toward German.
    assert prompt.rstrip().endswith("Antwort (auf Deutsch):")
    assert "Anfrage des Nutzers" in prompt  # German user-turn label


def test_typed_german_chat_keeps_english_labels_and_no_priming():
    from backend.app.services.chat_orchestrator import _build_prompt_text

    # for_speech=False (typed chat) must be unaffected by the voice-only German framing.
    prompt = _build_prompt_text(_req(lang="de", for_speech=False))
    assert "User request" in prompt
    assert "Antwort (auf Deutsch):" not in prompt


def test_speech_instruction_locks_language_to_english():
    instruction = _system_instruction(_req(lang="en", for_speech=True))
    assert "Respond only in en" in instruction
    assert "always answer in en" in instruction


def test_speech_instruction_keeps_citation_markers_with_context_english():
    instruction = _system_instruction(_req(ctx="- [S1] etwas", lang="en", for_speech=True))
    assert "[S3]" in instruction
    assert "removed before speaking" in instruction.lower()


def test_speech_instruction_keeps_citation_markers_with_context_german():
    instruction = _system_instruction(_req(ctx="- [S1] etwas", lang="de", for_speech=True))
    assert "[S3]" in instruction
    assert "vor dem Vorlesen entfernt" in instruction


def test_user_content_omits_context_section_when_empty():
    content = _build_user_content(_req(ctx=""))
    assert "Transcript context" not in content
    assert "User request" in content


def test_user_content_includes_context_when_present():
    assert "Transcript context" in _build_user_content(_req(ctx="- ctx line"))


def test_language_detection_german_vs_english():
    detect = ChatOrchestrator._detect_response_language
    assert detect("Was ist der Plan für das Meeting?") == "de"
    assert detect("What is the plan for the meeting today?") == "en"
    assert detect("Erzähl mir mehr über München.") == "de"  # umlaut marker


def _hit(index: int, words: int, score: float = 1.0) -> RetrievalHit:
    chunk = RetrievalChunk(
        chunk_id=f"seg-{index}",
        segment_id=str(index),
        segment_index=index,
        start_ms=index * 30_000,
        end_ms=(index + 1) * 30_000,
        speaker_name="SPEAKER_00",
        text=" ".join(["wort"] * words),
    )
    return RetrievalHit(chunk=chunk, score=score)


def test_context_is_capped_by_tokens_not_segment_count():
    # 60 speaker turns of 75 words (214 estimated tokens each) exceed the retrieval budget.
    turns = [_hit(i, 75) for i in range(60)]

    kept = _within_token_budget(turns, _RETRIEVAL_CONTEXT_TOKENS)

    assert [h.chunk.segment_index for h in kept] == list(range(28))  # 28 * 214 = 5992
    assert sum(_estimated_context_tokens(h) for h in kept) <= _RETRIEVAL_CONTEXT_TOKENS


def test_short_turns_count_their_per_line_markup():
    # Short dialogue turns are mostly timestamp/speaker/[SEG:] markup: 300 words in 100
    # lines cost far more prompt tokens than 300 words in 4 long turns.
    short = [_hit(i, 3) for i in range(100)]
    long = [_hit(i, 75) for i in range(4)]

    assert sum(map(_estimated_context_tokens, short)) > 3 * sum(
        map(_estimated_context_tokens, long)
    )


def test_token_budget_keeps_priority_order_and_at_least_one_hit():
    ranked = [_hit(7, 1500, 0.9), _hit(2, 1000, 0.5), _hit(5, 1000, 0.4)]

    assert [h.chunk.segment_index for h in _within_token_budget(ranked, 6000)] == [7, 2]
    assert [h.chunk.segment_index for h in _within_token_budget([_hit(1, 9000)], 6000)] == [1]


def test_full_transcript_budget_fills_the_context_window(monkeypatch):
    monkeypatch.delenv("TRANSCIBIO_OLLAMA_NUM_CTX", raising=False)
    assert _full_transcript_context_tokens() == 131072 - _PROMPT_AND_ANSWER_RESERVE_TOKENS

    monkeypatch.setenv("TRANSCIBIO_OLLAMA_NUM_CTX", "65536")
    assert _full_transcript_context_tokens() == 65536 - _PROMPT_AND_ANSWER_RESERVE_TOKENS


def test_ollama_payload_uses_shared_num_ctx_for_typed_and_voice(monkeypatch):
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_NUM_CTX", "65536")
    client = OllamaChatModelClient(model_name="gemma4:26b", url="http://ollama.test")

    typed = client._build_payload(_req(), stream=False)
    voice = client._build_payload(_req(for_speech=True), stream=True, think=False)

    assert typed["options"]["num_ctx"] == voice["options"]["num_ctx"] == 65536


def test_typed_chat_disables_reasoning_by_default(monkeypatch):
    monkeypatch.delenv("TRANSCIBIO_OLLAMA_THINK", raising=False)
    client = OllamaChatModelClient(model_name="gemma4:26b", url="http://ollama.test")

    think = client._think_for(_req())

    assert think is False
    assert client._build_payload(_req(), stream=False, think=think)["think"] is False


def test_typed_chat_uses_model_default_reasoning_when_enabled(monkeypatch):
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_THINK", "true")
    client = OllamaChatModelClient(model_name="gemma4:26b", url="http://ollama.test")

    think = client._think_for(_req())

    assert think is None
    assert "think" not in client._build_payload(_req(), stream=False, think=think)


def test_voice_turns_never_reason_even_when_enabled(monkeypatch):
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_THINK", "true")
    client = OllamaChatModelClient(model_name="gemma4:26b", url="http://ollama.test")

    assert client._think_for(_req(for_speech=True)) is False


def test_client_think_switch_overrides_env(monkeypatch):
    # The Settings switch reaches the client via LocalLlmConfig.think.
    monkeypatch.setenv("TRANSCIBIO_OLLAMA_THINK", "false")
    on = OllamaChatModelClient(model_name="gemma4:26b", url="http://ollama.test", think=True)
    assert on._think_for(_req()) is None  # no `think` field -> model default (reasons)
    assert on._think_for(_req(for_speech=True)) is False  # voice never reasons

    monkeypatch.setenv("TRANSCIBIO_OLLAMA_THINK", "true")
    off = OllamaChatModelClient(model_name="gemma4:26b", url="http://ollama.test", think=False)
    assert off._think_for(_req()) is False


# --- Citations: tolerant resolution (models don't always copy the id) ---


def _ref_hit(segment_id: str, start_ms: int, end_ms: int):
    from types import SimpleNamespace

    chunk = SimpleNamespace(
        segment_id=segment_id, segment_index=start_ms, start_ms=start_ms, end_ms=end_ms
    )
    return SimpleNamespace(chunk=chunk)


def test_citation_refs_resolve_ids_prefixes_lists_and_times():
    from backend.app.services.chat_orchestrator import _resolve_citation_refs

    hits = [
        _ref_hit("4aa4c172d34e44739895f65ea205030f", 192_000, 195_000),
        _ref_hit("fd4cd766f95145cc8cc88aec519226aa", 247_000, 252_000),
    ]
    assert _resolve_citation_refs("4aa4c172d34e44739895f65ea205030f", hits) == [
        hits[0].chunk.segment_id
    ]
    assert _resolve_citation_refs("fd4cd766", hits) == [hits[1].chunk.segment_id]  # shortened
    assert _resolve_citation_refs(
        "4aa4c172d34e44739895f65ea205030f, SEG:fd4cd766f95145cc8cc88aec519226aa", hits
    ) == [hits[0].chunk.segment_id, hits[1].chunk.segment_id]
    # Models sometimes cite times instead of ids.
    assert _resolve_citation_refs("03:12-03:15, 04:07-04:12", hits) == [
        hits[0].chunk.segment_id,
        hits[1].chunk.segment_id,
    ]
    assert _resolve_citation_refs("deadbeef00", hits) == []  # not in the context
    # Short source numbers (S1 = first context line in transcript order), lists, ranges.
    assert _resolve_citation_refs("S2", hits) == [hits[1].chunk.segment_id]
    assert _resolve_citation_refs("S1, S2", hits) == [
        hits[0].chunk.segment_id,
        hits[1].chunk.segment_id,
    ]
    assert _resolve_citation_refs("S1–S2", hits) == [
        hits[0].chunk.segment_id,
        hits[1].chunk.segment_id,
    ]
    assert _resolve_citation_refs("S9", hits) == []


def test_marker_pattern_catches_bare_ids_and_source_numbers_but_not_footnotes():
    from backend.app.services.chat_orchestrator import _CITATION_MARKER_RE

    # A voice answer cited the bare id without "SEG:"; it must not reach the screen or TTS.
    text = "Herr Wagner ist der Kunde [db3c645756024473ad26e7cbed798571]. Ja [S3, S7]."
    assert _CITATION_MARKER_RE.sub("", text) == "Herr Wagner ist der Kunde . Ja ."
    # Footnotes, markdown links and ordinary brackets stay.
    for keep in ("[1] 00:01-00:05 (Anna)", "[Link](https://x.de)", "[Sprecher 1]", "[Seite 3]"):
        assert _CITATION_MARKER_RE.sub("", keep) == keep


def test_context_lines_put_the_id_first_and_no_time_in_brackets():
    from types import SimpleNamespace

    from backend.app.services.chat_orchestrator import ChatOrchestrator

    chunk = SimpleNamespace(
        segment_id="a1b2c3",
        segment_index=0,
        start_ms=0,
        end_ms=5000,
        speaker_name="Anna",
        text="Wir starten.",
    )
    line = ChatOrchestrator._format_context_for_model([SimpleNamespace(chunk=chunk)])
    assert line == "- [S1] 00:00–00:05, Anna: Wir starten."


def test_app_context_reaches_typed_and_voice_prompts():
    typed = _system_instruction(
        ChatModelRequest(
            user_message="Wie funktioniert das?",
            transcript_context="",
            response_language="de",
            app_context="Über Transcibio: ...",
        )
    )
    voice = _system_instruction(
        ChatModelRequest(
            user_message="Wie funktioniert das?",
            transcript_context="",
            response_language="de",
            for_speech=True,
            app_context="Über Transcibio: ...",
        )
    )
    assert "Über Transcibio" in typed and "Über Transcibio" in voice
