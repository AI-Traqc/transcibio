from backend.app.services.text_chunking import SentenceChunker


def _drain(tokens: list[str], **kwargs) -> list[str]:
    chunker = SentenceChunker(**kwargs)
    out: list[str] = []
    for token in tokens:
        out.extend(chunker.push(token))
    tail = chunker.flush()
    if tail:
        out.append(tail)
    return out


def test_splits_on_sentence_boundaries():
    out = _drain(list("Erstens. Zweitens! Drittens?"))
    assert out == ["Erstens.", "Zweitens!", "Drittens?"]


def test_does_not_split_on_german_abbreviations():
    out = _drain(["Wir treffen uns z.", "B. am Montag, d.", "h. morgen früh. ", "Okay?"])
    assert out == ["Wir treffen uns z.B. am Montag, d.h. morgen früh.", "Okay?"]


def test_does_not_split_on_decimals_or_ordinals():
    out = _drain(["Es kostet 3.14 Euro und am 1. ", "Januar geht es los. ", "Ende."])
    assert out == ["Es kostet 3.14 Euro und am 1. Januar geht es los.", "Ende."]


def test_first_chunk_flushes_early_on_clause_boundary():
    # A long first sentence should emit an early clause chunk to cut TTFA, rather than
    # waiting for the final period. The clause boundary clears min_chunk_chars, so the
    # early flush prefers it over a bare word break.
    text = (
        "Ich begrüße Sie herzlich zu unserer heutigen Demonstration, "
        "die jetzt ausführlich beginnt und gleich weitergeht."
    )
    out = _drain(list(text), first_chunk_max_chars=90)
    assert out[0] == "Ich begrüße Sie herzlich zu unserer heutigen Demonstration,"
    assert len(out) >= 2
    # Reassembled chunks preserve the full text (ignoring whitespace).
    assert "".join(out).replace(" ", "") == text.replace(" ", "")


def test_tiny_leading_clause_is_not_split_off():
    # A clause boundary below min_chunk_chars must NOT become the first utterance — a
    # tiny fragment like "Ja," gets unnatural sentence-final intonation from the TTS.
    # The early flush falls back to a later word break instead.
    text = (
        "Ja, dies ist ein bewusst sehr langer erster Satz ohne weitere "
        "Satzzeichen der einfach immer weiter laeuft."
    )
    out = _drain(list(text), first_chunk_max_chars=90)
    assert out[0] != "Ja,"
    assert not out[0].endswith(",")
    assert len(out) >= 2
    assert "".join(out).replace(" ", "") == text.replace(" ", "")


def test_word_break_fallback_when_no_clause_in_budget():
    # No clause punctuation within the budget -> split at the last word break.
    text = "Guten Tag und herzlich willkommen zu dieser ausführlichen Demonstration."
    out = _drain(list(text), first_chunk_max_chars=40)
    assert len(out) >= 2
    assert not out[0].endswith(".")
    assert "".join(out).replace(" ", "") == text.replace(" ", "")


def test_flush_returns_trailing_text_without_terminator():
    out = _drain(["Kein Satzende hier"])
    assert out == ["Kein Satzende hier"]


def test_empty_input_yields_nothing():
    assert _drain([""]) == []
    assert _drain([]) == []
