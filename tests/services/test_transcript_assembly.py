from dataclasses import dataclass

from backend.app.services.diarization import DiarizationAttemptResult, DiarizationSpeakerSegment
from backend.app.services.stt import SttResult, SttSegment, SttWord
from backend.app.services.transcript_assembly import UNKNOWN_SPEAKER_KEY, TranscriptAssemblyService
from backend.app.store import SQLiteStore


@dataclass(frozen=True)
class StoredSegment:
    speaker: str
    text: str
    start_ms: int
    end_ms: int
    word_indexes: tuple[int, ...]


def _chunk(*words: tuple[str, float, float]) -> SttSegment:
    """One STT segment (e.g. a 30 s batched chunk) built from (word, start, end) triples."""
    return SttSegment(
        text=" ".join(text for text, _, _ in words),
        start_seconds=words[0][1],
        end_seconds=words[-1][2],
        words=tuple(SttWord(text=text, start_seconds=s, end_seconds=e) for text, s, e in words),
    )


def _sentence(text: str, start: float, end: float) -> list[tuple[str, float, float]]:
    """Spread a sentence's words evenly over [start, end]."""
    tokens = text.split()
    step = (end - start) / len(tokens)
    return [(tok, start + i * step, start + (i + 1) * step) for i, tok in enumerate(tokens)]


def _persist(tmp_path, *segments: SttSegment, speakers=()) -> list[StoredSegment]:
    store = SQLiteStore(tmp_path / "test.db")
    store.initialize()
    session = store.create_session(title="Test", source_kind="typed")
    diarization = DiarizationAttemptResult(
        segments=tuple(DiarizationSpeakerSegment(s, e, key) for s, e, key in speakers),
        used=bool(speakers),
    )
    result = TranscriptAssemblyService(store).persist_initial_revision(
        session_id=session.id,
        stt_result=SttResult(
            text=" ".join(seg.text for seg in segments),
            segments=segments,
            detected_language="de",
            detected_language_probability=0.99,
            model_name="medium",
            mode="meeting",
            preset="balanced",
        ),
        diarization=diarization,
    )
    words = store.list_transcript_words_for_revision(result.revision_id)
    stored = []
    for seg in store.list_transcript_segments(result.revision_id):
        speaker = store.get_transcript_speaker(seg.speaker_id) if seg.speaker_id else None
        stored.append(
            StoredSegment(
                speaker=speaker.speaker_key if speaker else UNKNOWN_SPEAKER_KEY,
                text=seg.text,
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                word_indexes=tuple(w.word_index for w in words if w.segment_id == seg.id),
            )
        )
    return stored


def test_chunk_spanning_two_speakers_is_split_at_their_sentences(tmp_path):
    # Real case from the sample recording: batched STT returns this as part of one chunk,
    # but the question and the answer come from different people.
    chunk = _chunk(
        *_sentence("Würde Ihnen das passen?", 190.0, 191.0),
        *_sentence("Mittwoch um 10 ist perfekt.", 191.2, 192.4),
        *_sentence("Wunderbar.", 192.9, 193.6),
    )
    speakers = [
        (185.0, 191.1, "SPEAKER_00"),
        (191.1, 192.6, "SPEAKER_01"),
        (192.6, 196.0, "SPEAKER_00"),
    ]

    stored = _persist(tmp_path, chunk, speakers=speakers)

    assert [(s.speaker, s.text) for s in stored] == [
        ("SPEAKER_00", "Würde Ihnen das passen?"),
        ("SPEAKER_01", "Mittwoch um 10 ist perfekt."),
        ("SPEAKER_00", "Wunderbar."),
    ]
    assert (stored[1].start_ms, stored[1].end_ms) == (191200, 192400)


def test_consecutive_same_speaker_sentences_merge_into_one_turn(tmp_path):
    first = _chunk(*_sentence("Guten Tag.", 0.0, 1.0), *_sentence("Hier ist Wagner.", 1.2, 2.5))
    second = _chunk(*_sentence("Ich rufe wegen der Dusche an.", 2.8, 5.0))  # next STT chunk

    stored = _persist(tmp_path, first, second, speakers=[(0.0, 6.0, "SPEAKER_00")])

    assert [(s.speaker, s.text) for s in stored] == [
        ("SPEAKER_00", "Guten Tag. Hier ist Wagner. Ich rufe wegen der Dusche an."),
    ]
    assert (stored[0].start_ms, stored[0].end_ms) == (0, 5000)
    # All 11 words kept, renumbered so (segment_id, word_index) stays unique.
    assert stored[0].word_indexes == tuple(range(11))


def test_turns_are_capped_at_30_seconds_without_diarization(tmp_path):
    monologue = _chunk(
        *[w for k in range(4) for w in _sentence(f"Satz Nummer {k}.", 10.0 * k, 10.0 * k + 10)]
    )

    stored = _persist(tmp_path, monologue)

    assert [(s.speaker, s.start_ms, s.end_ms) for s in stored] == [
        (UNKNOWN_SPEAKER_KEY, 0, 30000),
        (UNKNOWN_SPEAKER_KEY, 30000, 40000),
    ]
    assert stored[0].text == "Satz Nummer 0. Satz Nummer 1. Satz Nummer 2."


def test_over_split_abbreviation_is_merged_back(tmp_path):
    # The punctuation rule splits after "z." — harmless, the same speaker rejoins it.
    chunk = _chunk(*_sentence("Wir treffen uns z. B. am Montag.", 0.0, 3.0))

    stored = _persist(tmp_path, chunk, speakers=[(0.0, 3.0, "SPEAKER_00")])

    assert [s.text for s in stored] == ["Wir treffen uns z. B. am Montag."]


def test_segment_without_words_is_kept_verbatim(tmp_path):
    segment = SttSegment(text="Hallo zusammen", start_seconds=0.0, end_seconds=2.0, words=())

    stored = _persist(tmp_path, segment)

    assert [(s.text, s.start_ms, s.end_ms) for s in stored] == [("Hallo zusammen", 0, 2000)]
