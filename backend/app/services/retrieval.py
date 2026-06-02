from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import AppSettings
from backend.app.store import SQLiteStore, TranscriptRevisionRecord

_TOKEN_RE = re.compile(r"[A-Za-z0-9ÄÖÜäöüß]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text or "")]


def _sparse_embed(text: str) -> dict[str, float]:
    counts: dict[str, int] = {}
    for token in _tokenize(text):
        counts[token] = counts.get(token, 0) + 1
    if not counts:
        return {}
    norm = math.sqrt(sum(value * value for value in counts.values()))
    if norm <= 0:
        return {}
    return {token: value / norm for token, value in counts.items()}


def _cosine_sparse(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    score = 0.0
    for key, value in left.items():
        score += value * right.get(key, 0.0)
    return float(score)


@dataclass(frozen=True)
class RetrievalChunk:
    chunk_id: str
    segment_id: str
    segment_index: int
    start_ms: int
    end_ms: int
    speaker_name: str
    text: str


@dataclass(frozen=True)
class RetrievalHit:
    chunk: RetrievalChunk
    score: float


@dataclass(frozen=True)
class IndexedTranscriptRevision:
    session_id: str
    revision_id: str
    revision_number: int
    vectors_path: str
    meta_path: str
    chunk_count: int


class TranscriptEmbeddingIndexer:
    """Local file-based transcript indexing using sparse lexical vectors (MVP fallback)."""

    def __init__(self, store: SQLiteStore, settings: AppSettings) -> None:
        self._store = store
        self._settings = settings

    def ensure_index(self, revision: TranscriptRevisionRecord) -> IndexedTranscriptRevision:
        transcript_dir = self._settings.sessions_root / revision.session_id / "transcript"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        base_name = f"revision_{revision.revision_number}"
        vectors_path = transcript_dir / f"{base_name}_embeddings.json"
        meta_path = transcript_dir / f"{base_name}_embedding_meta.json"
        if vectors_path.exists() and meta_path.exists():
            try:
                meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
                chunk_count = int(meta_payload.get("chunk_count", 0))
            except Exception:
                chunk_count = 0
            return IndexedTranscriptRevision(
                session_id=revision.session_id,
                revision_id=revision.id,
                revision_number=revision.revision_number,
                vectors_path=self._relative_data_path(vectors_path),
                meta_path=self._relative_data_path(meta_path),
                chunk_count=chunk_count,
            )

        speakers = self._store.list_transcript_speakers(revision.id)
        segments = self._store.list_transcript_segments(revision.id)
        speaker_map = {speaker.id: speaker for speaker in speakers}

        chunks: list[RetrievalChunk] = []
        vectors: list[dict[str, object]] = []
        for segment in segments:
            speaker_name = "Unknown"
            if segment.speaker_id and segment.speaker_id in speaker_map:
                speaker_rec = speaker_map[segment.speaker_id]
                speaker_name = speaker_rec.display_name or speaker_rec.speaker_key
            chunk = RetrievalChunk(
                chunk_id=f"seg-{segment.id}",
                segment_id=segment.id,
                segment_index=segment.segment_index,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                speaker_name=speaker_name,
                text=segment.text,
            )
            chunks.append(chunk)
            vectors.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "segment_id": chunk.segment_id,
                    "vector": _sparse_embed(chunk.text),
                }
            )

        meta_payload = {
            "session_id": revision.session_id,
            "revision_id": revision.id,
            "revision_number": revision.revision_number,
            "chunk_count": len(chunks),
            "chunks": [chunk.__dict__ for chunk in chunks],
        }
        vectors_payload = {
            "session_id": revision.session_id,
            "revision_id": revision.id,
            "revision_number": revision.revision_number,
            "vectors": vectors,
        }
        meta_path.write_text(
            json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        vectors_path.write_text(json.dumps(vectors_payload, ensure_ascii=False), encoding="utf-8")

        return IndexedTranscriptRevision(
            session_id=revision.session_id,
            revision_id=revision.id,
            revision_number=revision.revision_number,
            vectors_path=self._relative_data_path(vectors_path),
            meta_path=self._relative_data_path(meta_path),
            chunk_count=len(chunks),
        )

    def load_chunks_and_vectors(
        self,
        *,
        revision: TranscriptRevisionRecord,
    ) -> tuple[list[RetrievalChunk], dict[str, dict[str, float]]]:
        self.ensure_index(revision)
        transcript_dir = self._settings.sessions_root / revision.session_id / "transcript"
        base_name = f"revision_{revision.revision_number}"
        vectors_path = transcript_dir / f"{base_name}_embeddings.json"
        meta_path = transcript_dir / f"{base_name}_embedding_meta.json"
        meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
        vectors_payload = json.loads(vectors_path.read_text(encoding="utf-8"))
        chunks = [RetrievalChunk(**item) for item in meta_payload.get("chunks", [])]
        vectors_by_segment_id: dict[str, dict[str, float]] = {}
        for item in vectors_payload.get("vectors", []):
            segment_id = str(item.get("segment_id", ""))
            vector = item.get("vector") or {}
            if segment_id and isinstance(vector, dict):
                vectors_by_segment_id[segment_id] = {
                    str(k): float(v)
                    for k, v in vector.items()
                    if isinstance(k, str) and isinstance(v, (int, float))
                }
        return chunks, vectors_by_segment_id

    def _relative_data_path(self, path: Path) -> str:
        return str(path.relative_to(self._settings.data_root)).replace("\\", "/")


class TranscriptRetriever:
    def __init__(self, store: SQLiteStore, settings: AppSettings) -> None:
        self._store = store
        self._indexer = TranscriptEmbeddingIndexer(store, settings)

    def index_revision(self, revision: TranscriptRevisionRecord) -> IndexedTranscriptRevision:
        return self._indexer.ensure_index(revision)

    def load_chunks_and_vectors(
        self,
        *,
        revision: TranscriptRevisionRecord,
    ) -> tuple[list[RetrievalChunk], dict[str, dict[str, float]]]:
        return self._indexer.load_chunks_and_vectors(revision=revision)

    def retrieve(
        self,
        *,
        revision: TranscriptRevisionRecord,
        query: str,
        top_k: int = 4,
        include_neighbors: bool = True,
    ) -> list[RetrievalHit]:
        chunks, vectors_by_segment_id = self._indexer.load_chunks_and_vectors(revision=revision)
        if not chunks:
            return []
        query_vec = _sparse_embed(query)
        if not query_vec:
            return []

        scored: list[RetrievalHit] = []
        for chunk in chunks:
            score = _cosine_sparse(query_vec, vectors_by_segment_id.get(chunk.segment_id, {}))
            if score > 0:
                scored.append(RetrievalHit(chunk=chunk, score=score))
        scored.sort(key=lambda hit: hit.score, reverse=True)
        if scored:
            base_hits = scored[: max(1, top_k)]
        else:
            # Fallback for generic prompts like "summarize the call" that may have no lexical overlap.
            base_hits = [
                RetrievalHit(chunk=chunk, score=0.0001) for chunk in chunks[: max(1, top_k)]
            ]

        if not include_neighbors or not base_hits:
            return base_hits

        chunks_by_index = {chunk.segment_index: chunk for chunk in chunks}
        selected: dict[str, RetrievalHit] = {hit.chunk.segment_id: hit for hit in base_hits}
        for hit in list(base_hits):
            for neighbor_index in (hit.chunk.segment_index - 1, hit.chunk.segment_index + 1):
                neighbor = chunks_by_index.get(neighbor_index)
                if neighbor is None or neighbor.segment_id in selected:
                    continue
                selected[neighbor.segment_id] = RetrievalHit(
                    chunk=neighbor, score=max(hit.score * 0.85, 0.0001)
                )

        return sorted(
            selected.values(),
            key=lambda item: (-item.score, item.chunk.segment_index),
        )
