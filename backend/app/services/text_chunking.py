"""Sentence chunking for streaming TTS.

Accumulates streamed LLM tokens and flushes *speakable* chunks on sentence
boundaries. To minimize time-to-first-audio the FIRST chunk is flushed early — on
the latest clause boundary (or word break) once a soft character budget is
reached — so audio starts after roughly a clause instead of a whole sentence.
Subsequent chunks wait for full sentence boundaries, which gives Piper/Kokoro
enough context for natural prosody.

German-aware: does not split after common abbreviations (``z. B.``, ``d. h.``,
``usw.``) or after a digit + period (decimals, versions, ordinals, dates).
"""

from __future__ import annotations

from dataclasses import dataclass, field

_SENTENCE_ENDINGS = ".!?…"
_CLAUSE_BOUNDARIES = ",;:—–"

# Abbreviations (spaces removed, no trailing dot) that end in a period but do not
# end a sentence. Compared case-insensitively against the trailing run of
# letters/dots before a candidate boundary.
_ABBREVIATIONS = frozenset(
    {
        "z.b",
        "d.h",
        "u.a",
        "u.v.m",
        "usw",
        "bzw",
        "ggf",
        "evtl",
        "inkl",
        "ca",
        "vgl",
        "etc",
        "nr",
        "abs",
        "bspw",
        "sog",
        "dr",
        "prof",
        "i.d.r",
        "o.ä",
        "u.u",
        "z.t",
        "max",
        "min",
        "ph",
        "tel",
        "str",
    }
)


@dataclass
class SentenceChunker:
    """Stateful, push-driven chunker. Not thread-safe (use one per stream)."""

    first_chunk_max_chars: int = 90
    # Floor for the early first-clause flush. Too low (e.g. 8) lets the very first
    # spoken fragment be a tiny clause that Piper reads with unnatural sentence-final
    # intonation; ~25 keeps the opening utterance long enough to sound natural while
    # still flushing well before the full sentence (first_chunk_max_chars).
    min_chunk_chars: int = 25
    _buffer: str = field(default="", init=False)
    _emitted_first: bool = field(default=False, init=False)

    def push(self, text: str) -> list[str]:
        """Feed streamed text; return any speakable chunks that just completed."""
        self._buffer += text
        chunks: list[str] = []
        while True:
            chunk = self._extract_one()
            if chunk is None:
                break
            chunks.append(chunk)
        return chunks

    def flush(self) -> str | None:
        """Return any remaining buffered text once the stream ends."""
        remaining = self._buffer.strip()
        self._buffer = ""
        if remaining:
            self._emitted_first = True
            return remaining
        return None

    def _extract_one(self) -> str | None:
        buf = self._buffer
        for i in range(len(buf) - 1):
            if buf[i] in _SENTENCE_ENDINGS and buf[i + 1].isspace():
                if self._is_sentence_boundary(buf, i):
                    return self._emit(i + 1)
        if not self._emitted_first and len(buf) >= self.first_chunk_max_chars:
            split = self._early_split_point(buf)
            if split is not None:
                return self._emit(split)
        return None

    def _emit(self, end: int) -> str | None:
        chunk = self._buffer[:end].strip()
        self._buffer = self._buffer[end:]
        if not chunk:
            return None
        self._emitted_first = True
        return chunk

    @staticmethod
    def _is_sentence_boundary(buf: str, dot_index: int) -> bool:
        before = buf[dot_index - 1] if dot_index > 0 else ""
        # Digit + period: decimal, version, ordinal, or date — keep going.
        if buf[dot_index] == "." and before.isdigit():
            return False
        # Trailing run of letters/dots forms a (possibly multi-dot) abbreviation.
        j = dot_index
        run: list[str] = []
        while j >= 0 and (buf[j].isalpha() or buf[j] == "."):
            run.append(buf[j])
            j -= 1
        token = "".join(reversed(run)).strip(".").lower()
        return token not in _ABBREVIATIONS

    def _early_split_point(self, buf: str) -> int | None:
        window = buf[: self.first_chunk_max_chars]
        for boundary in _CLAUSE_BOUNDARIES:
            idx = window.rfind(boundary)
            if idx >= self.min_chunk_chars:
                return idx + 1
        space = window.rfind(" ")
        if space >= self.min_chunk_chars:
            return space + 1
        return None
