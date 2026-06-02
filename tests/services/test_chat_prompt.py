from backend.app.services.chat_orchestrator import (
    ChatModelRequest,
    ChatOrchestrator,
    _build_user_content,
    _system_instruction,
)


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
    instruction = _system_instruction(_req(ctx="- [SEG:x] etwas"))
    assert "transcript" in instruction.lower()
    assert "[SEG:" in instruction
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
    instruction = _system_instruction(_req(ctx="- [SEG:x] etwas", lang="en", for_speech=True))
    assert "[SEG:" in instruction
    assert "removed before speaking" in instruction.lower()


def test_speech_instruction_keeps_citation_markers_with_context_german():
    instruction = _system_instruction(_req(ctx="- [SEG:x] etwas", lang="de", for_speech=True))
    assert "[SEG:" in instruction
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
