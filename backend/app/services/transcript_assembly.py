from __future__ import annotations

import re
from dataclasses import dataclass, replace

from backend.app.services.diarization import DiarizationAttemptResult, DiarizationSpeakerSegment
from backend.app.services.stt import SttResult, SttSegment, SttWord
from backend.app.store import (
    SQLiteStore,
    TranscriptSegmentInput,
    TranscriptSpeakerInput,
    TranscriptWordInput,
)

UNKNOWN_SPEAKER_KEY = "UNKNOWN_SPEAKER"

# A word ending in sentence punctuation (optionally followed by closing quotes).
_SENTENCE_END = re.compile(r"[.!?…][\"'»«“”„]*$")
# Upper bound for one speaker turn; keeps UI rows, retrieval chunks and correction
# prompts bounded (~75 words of speech).
_MAX_TURN_MS = 30_000


@dataclass(frozen=True)
class TranscriptAssemblyResult:
    revision_id: str
    revision_number: int
    full_text: str
    diarization_used: bool
    speaker_count: int
    segment_count: int
    word_count: int
    warnings: tuple[str, ...]


class TranscriptAssemblyService:
    """Builds and persists transcript revisions from STT + optional diarization.

    Segments are speaker turns: STT segments (batched STT returns chunks of up to 30 s)
    are split into sentences by word timestamps, each sentence gets the speaker it
    overlaps most, and consecutive sentences of one speaker are merged into a turn of at
    most `_MAX_TURN_MS`. So one segment never mixes two speakers' sentences.
    """

    def __init__(self, store: SQLiteStore) -> None:
        self._store = store

    def persist_initial_revision(
        self,
        *,
        session_id: str,
        stt_result: SttResult,
        diarization: DiarizationAttemptResult | None = None,
        additional_warnings: tuple[str, ...] | list[str] = (),
        created_by: str = "system",
        source: str = "initial_transcription",
    ) -> TranscriptAssemblyResult:
        diarization_result = diarization or DiarizationAttemptResult(
            segments=(), used=False, warnings=()
        )
        segment_inputs = self._build_segment_inputs(stt_result, diarization_result)
        speaker_inputs = self._build_speaker_inputs(segment_inputs)

        full_text = self._build_full_text(segment_inputs, fallback_text=stt_result.text)
        warnings = tuple(list(additional_warnings) + list(diarization_result.warnings))

        create_result = self._store.create_transcript_revision(
            session_id=session_id,
            created_by=created_by,
            source=source,
            full_text=full_text,
            language_detected=stt_result.detected_language or "",
            diarization_used=diarization_result.used,
            stt_model=stt_result.model_name,
            warnings=warnings,
            speakers=tuple(speaker_inputs),
            segments=tuple(segment_inputs),
            parent_revision_id=None,
            set_session_status="ready",
        )

        total_words = sum(len(seg.words) if seg.words else seg.word_count for seg in segment_inputs)
        return TranscriptAssemblyResult(
            revision_id=create_result.revision.id,
            revision_number=create_result.revision.revision_number,
            full_text=create_result.revision.full_text,
            diarization_used=create_result.revision.diarization_used,
            speaker_count=len(speaker_inputs),
            segment_count=len(segment_inputs),
            word_count=total_words,
            warnings=warnings,
        )

    def _build_segment_inputs(
        self,
        stt_result: SttResult,
        diarization_result: DiarizationAttemptResult,
    ) -> list[TranscriptSegmentInput]:
        diar_segments = diarization_result.segments
        built: list[TranscriptSegmentInput] = []

        if not stt_result.segments:
            fallback_text = (stt_result.text or "").strip()
            if not fallback_text:
                return built
            built.append(
                TranscriptSegmentInput(
                    segment_index=0,
                    speaker_key=UNKNOWN_SPEAKER_KEY,
                    start_ms=0,
                    end_ms=0,
                    text=fallback_text,
                    word_count=len(fallback_text.split()),
                    words=(),
                )
            )
            return built

        for seg in stt_result.segments:
            for sentence in self._split_into_sentences(seg):
                normalized = self._segment_to_input(
                    idx=len(built),
                    segment=sentence,
                    diarization_segments=diar_segments,
                )
                if normalized is not None:
                    built.append(normalized)
        turns = self._merge_speaker_turns(built)
        return [replace(turn, segment_index=idx) for idx, turn in enumerate(turns)]

    @staticmethod
    def _split_into_sentences(segment: SttSegment) -> list[SttSegment]:
        """Cut a segment after every word that ends in sentence punctuation.

        A plain punctuation rule is enough: splitting too often (e.g. after "z." in
        "z. B.") is harmless because same-speaker pieces are merged back into one turn.
        Splitting too rarely would leave two speakers in one segment.
        """
        sentences: list[list[SttWord]] = [[]]
        for word in segment.words:
            sentences[-1].append(word)
            if _SENTENCE_END.search(word.text.strip()):
                sentences.append([])
        sentences = [words for words in sentences if words]
        if len(sentences) <= 1:
            return [segment]  # nothing to split; keep the original text verbatim
        return [
            SttSegment(
                text=" ".join(w.text.strip() for w in words if w.text.strip()),
                start_seconds=words[0].start_seconds,
                end_seconds=words[-1].end_seconds,
                words=tuple(words),
            )
            for words in sentences
        ]

    @staticmethod
    def _merge_speaker_turns(
        segments: list[TranscriptSegmentInput],
    ) -> list[TranscriptSegmentInput]:
        """Join consecutive same-speaker segments into turns of at most `_MAX_TURN_MS`."""
        turns: list[TranscriptSegmentInput] = []
        for seg in segments:
            prev = turns[-1] if turns else None
            if (
                prev is None
                or prev.speaker_key != seg.speaker_key
                or seg.end_ms <= seg.start_ms  # no timing: can't bound the turn length
                or seg.end_ms - prev.start_ms > _MAX_TURN_MS
            ):
                turns.append(seg)
                continue
            words = (*prev.words, *seg.words)
            turns[-1] = replace(
                prev,
                end_ms=max(prev.end_ms, seg.end_ms),
                text=f"{prev.text} {seg.text}",
                word_count=prev.word_count + seg.word_count,
                words=tuple(replace(word, word_index=i) for i, word in enumerate(words)),
            )
        return turns

    def _segment_to_input(
        self,
        *,
        idx: int,
        segment: SttSegment,
        diarization_segments: tuple[DiarizationSpeakerSegment, ...],
    ) -> TranscriptSegmentInput | None:
        text = (segment.text or "").strip()
        words = tuple(self._words_from_stt(segment.words))

        start_seconds = segment.start_seconds
        end_seconds = segment.end_seconds
        if (start_seconds is None or end_seconds is None) and words:
            starts = [w.start_ms for w in words if w.start_ms is not None]
            ends = [w.end_ms for w in words if w.end_ms is not None]
            if starts:
                start_seconds = min(starts) / 1000.0
            if ends:
                end_seconds = max(ends) / 1000.0

        start_ms = self._seconds_to_ms(start_seconds)
        end_ms = self._seconds_to_ms(end_seconds)
        if end_ms < start_ms:
            end_ms = start_ms

        if not text and not words:
            return None
        if not text and words:
            text = " ".join(w.word for w in words if w.word).strip()

        speaker_key = self._resolve_speaker_for_interval(
            start_ms=start_ms,
            end_ms=end_ms,
            diarization_segments=diarization_segments,
        )

        word_count = len([w for w in words if w.word.strip()]) or len(text.split())
        return TranscriptSegmentInput(
            segment_index=idx,
            speaker_key=speaker_key,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            confidence=None,
            word_count=word_count,
            words=words,
        )

    @staticmethod
    def _words_from_stt(words: tuple[SttWord, ...]) -> list[TranscriptWordInput]:
        converted: list[TranscriptWordInput] = []
        for idx, word in enumerate(words):
            token_text = (word.text or "").strip()
            if not token_text:
                continue
            converted.append(
                TranscriptWordInput(
                    word_index=idx,
                    word=token_text,
                    start_ms=TranscriptAssemblyService._seconds_to_ms(word.start_seconds),
                    end_ms=TranscriptAssemblyService._seconds_to_ms(word.end_seconds),
                    confidence=word.probability,
                )
            )
        return converted

    @staticmethod
    def _build_full_text(
        segments: list[TranscriptSegmentInput],
        *,
        fallback_text: str,
    ) -> str:
        text = "\n".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()
        if text:
            return text
        return (fallback_text or "").strip()

    @staticmethod
    def _build_speaker_inputs(
        segments: list[TranscriptSegmentInput],
    ) -> list[TranscriptSpeakerInput]:
        seen: dict[str, int] = {}
        for seg in segments:
            key = seg.speaker_key or UNKNOWN_SPEAKER_KEY
            if key not in seen:
                seen[key] = len(seen)
        return [
            TranscriptSpeakerInput(
                speaker_key=key,
                display_name=key,
                sort_order=order,
            )
            for key, order in seen.items()
        ]

    @staticmethod
    def _resolve_speaker_for_interval(
        *,
        start_ms: int,
        end_ms: int,
        diarization_segments: tuple[DiarizationSpeakerSegment, ...],
    ) -> str:
        if not diarization_segments:
            return UNKNOWN_SPEAKER_KEY
        if end_ms <= start_ms:
            midpoint_ms = start_ms
            for seg in diarization_segments:
                if (
                    TranscriptAssemblyService._seconds_to_ms(seg.start_seconds)
                    <= midpoint_ms
                    < TranscriptAssemblyService._seconds_to_ms(seg.end_seconds)
                ):
                    return seg.speaker_key
            return UNKNOWN_SPEAKER_KEY

        best_speaker = UNKNOWN_SPEAKER_KEY
        best_overlap = 0
        for diar_seg in diarization_segments:
            ds = TranscriptAssemblyService._seconds_to_ms(diar_seg.start_seconds)
            de = TranscriptAssemblyService._seconds_to_ms(diar_seg.end_seconds)
            overlap = min(end_ms, de) - max(start_ms, ds)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = diar_seg.speaker_key

        if best_overlap > 0:
            return best_speaker

        midpoint_ms = start_ms + ((end_ms - start_ms) // 2)
        for diar_seg in diarization_segments:
            ds = TranscriptAssemblyService._seconds_to_ms(diar_seg.start_seconds)
            de = TranscriptAssemblyService._seconds_to_ms(diar_seg.end_seconds)
            if ds <= midpoint_ms < de:
                return diar_seg.speaker_key
        return UNKNOWN_SPEAKER_KEY

    @staticmethod
    def _seconds_to_ms(value: float | None) -> int:
        if value is None:
            return 0
        try:
            return max(0, int(round(float(value) * 1000)))
        except (TypeError, ValueError):
            return 0
