from backend.app.services.chat_orchestrator import (
    _markdown_to_plain_text,
    _strip_for_speech,
)


def test_strips_numbered_lists():
    out = _strip_for_speech("1. Erstens\n2. Zweitens\n3. Drittens")
    assert "1." not in out and "2." not in out and "3." not in out
    assert out == "Erstens Zweitens Drittens"


def test_strips_all_bullets_not_just_the_first():
    out = _strip_for_speech("- erster Punkt\n- zweiter Punkt\n- dritter Punkt")
    assert "-" not in out
    assert out == "erster Punkt zweiter Punkt dritter Punkt"


def test_strips_table_pipes_and_separator_rows():
    out = _strip_for_speech("| Spalte A | Spalte B |\n|---|---|\n| eins | zwei |")
    assert "|" not in out
    assert "---" not in out
    assert "Spalte A" in out and "eins" in out


def test_unwraps_links_and_drops_url():
    out = _strip_for_speech("Siehe [diesen Link](https://example.com) hier.")
    assert "diesen Link" in out
    assert "http" not in out and "example.com" not in out
    assert "[" not in out and "]" not in out and "(" not in out


def test_strips_images():
    out = _strip_for_speech("![ein Bild](https://example.com/x.png) Ende")
    assert "http" not in out and "png" not in out
    assert "ein Bild" in out and "Ende" in out


def test_strips_headings_emphasis_code_and_citation_markers():
    out = _strip_for_speech("## Überschrift mit **fett**, `code` und [SEG:abc123].")
    assert "#" not in out and "*" not in out and "`" not in out
    assert "[SEG:" not in out
    assert "Überschrift mit fett, code und ." in out or "Überschrift mit fett, code und" in out


def test_drops_code_fences_but_keeps_inner_text():
    out = _strip_for_speech("```python\nprint('hi')\n```")
    assert "```" not in out
    assert "python" not in out  # fence-language token dropped with the fence line
    assert "print('hi')" in out


def test_fixes_space_before_punctuation():
    # Inline-code span ending a sentence used to leave "code ."
    out = _strip_for_speech("Das ist `code`.")
    assert "code." in out
    assert " ." not in out


def test_blockquote_marker_removed():
    out = _strip_for_speech("> Zitat hier")
    assert out == "Zitat hier"


def test_plain_text_passes_through_unchanged():
    out = _strip_for_speech("Der Plan ist einfach und klar.")
    assert out == "Der Plan ist einfach und klar."


# --- _markdown_to_plain_text (display/persistence) ---


def test_plain_text_helper_removes_markdown_but_keeps_line_breaks():
    md = "## Plan\n\n- Punkt eins\n- Punkt zwei\n\n1. Erstens\n2. Zweitens"
    out = _markdown_to_plain_text(md)
    for token in ("#", "*", "- ", "1.", "2."):
        assert token not in out
    assert "Plan" in out and "Punkt eins" in out and "Erstens" in out
    # Line breaks are preserved (unlike the speech strip which collapses them).
    assert "\n" in out


def test_plain_text_helper_strips_tables_and_links():
    md = "Siehe [Link](https://example.com).\n\n| A | B |\n|---|---|\n| 1 | 2 |"
    out = _markdown_to_plain_text(md)
    assert "http" not in out and "|" not in out and "---" not in out
    assert "Link" in out and "A" in out and "1" in out


def test_plain_text_helper_keeps_citation_footnotes_legible():
    md = "Die Antwort ist klar.\n\n[1] 00:00-00:05 (Anna)"
    out = _markdown_to_plain_text(md)
    assert "[1] 00:00-00:05 (Anna)" in out
    assert "Die Antwort ist klar." in out
