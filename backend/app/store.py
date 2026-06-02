from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SessionRecord:
    id: str
    created_at_utc: str
    updated_at_utc: str
    title: str
    source_kind: str
    source_name: str
    source_language_hint: str
    command_language_hint: str
    status: str
    last_error: str
    active_transcript_revision_id: str | None


@dataclass(frozen=True)
class JobRecord:
    id: str
    session_id: str | None
    job_type: str
    status: str
    progress: float
    created_at_utc: str
    started_at_utc: str | None
    finished_at_utc: str | None
    input_json: str
    output_json: str
    error_message: str


@dataclass(frozen=True)
class AudioAssetRecord:
    id: str
    session_id: str
    kind: str
    mime_type: str
    file_path: str
    duration_ms: int
    sample_rate_hz: int | None
    channels: int | None
    created_at_utc: str


@dataclass(frozen=True)
class TranscriptRevisionRecord:
    id: str
    session_id: str
    revision_number: int
    created_at_utc: str
    created_by: str
    source: str
    parent_revision_id: str | None
    full_text: str
    language_detected: str
    diarization_used: bool
    stt_model: str
    warnings_json: str


@dataclass(frozen=True)
class TranscriptSpeakerInput:
    speaker_key: str
    display_name: str
    sort_order: int


@dataclass(frozen=True)
class TranscriptWordInput:
    word_index: int
    word: str
    start_ms: int | None
    end_ms: int | None
    confidence: float | None = None


@dataclass(frozen=True)
class TranscriptSegmentInput:
    segment_index: int
    speaker_key: str | None
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None
    word_count: int = 0
    embedding_vector_ref: str | None = None
    words: tuple[TranscriptWordInput, ...] = ()


@dataclass(frozen=True)
class TranscriptRevisionCreateResult:
    revision: TranscriptRevisionRecord
    speaker_ids_by_key: dict[str, str]
    segment_ids: tuple[str, ...]


@dataclass(frozen=True)
class TranscriptSpeakerRecord:
    id: str
    revision_id: str
    speaker_key: str
    display_name: str
    sort_order: int


@dataclass(frozen=True)
class TranscriptSegmentRecord:
    id: str
    revision_id: str
    segment_index: int
    speaker_id: str | None
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None
    word_count: int
    embedding_vector_ref: str | None


@dataclass(frozen=True)
class TranscriptWordRecord:
    id: str
    segment_id: str
    word_index: int
    start_ms: int | None
    end_ms: int | None
    word: str
    confidence: float | None


@dataclass(frozen=True)
class ChatThreadRecord:
    id: str
    session_id: str
    created_at_utc: str
    updated_at_utc: str
    title: str


@dataclass(frozen=True)
class ChatMessageRecord:
    id: str
    thread_id: str
    session_id: str
    transcript_revision_id: str | None
    role: str
    content_markdown: str
    content_plain_text: str
    source_kind: str
    status: str
    model_name: str
    created_at_utc: str
    metadata_json: str


@dataclass(frozen=True)
class MessageCitationRecord:
    id: str
    message_id: str
    citation_index: int
    segment_id: str
    start_ms: int
    end_ms: int
    quote_excerpt: str


@dataclass(frozen=True)
class MessageCitationInput:
    citation_index: int
    segment_id: str
    start_ms: int
    end_ms: int
    quote_excerpt: str


@dataclass(frozen=True)
class VoiceCommandRecord:
    id: str
    session_id: str
    thread_id: str
    audio_asset_id: str
    transcribed_text: str
    edited_text: str
    send_mode: str
    detected_language: str
    stt_model: str
    created_at_utc: str
    sent_message_id: str | None


@dataclass(frozen=True)
class ActionProposalRecord:
    id: str
    session_id: str
    thread_id: str
    message_id: str
    action_type: str
    title: str
    status: str
    requires_confirmation: bool
    payload_json: str
    preview_markdown: str
    created_at_utc: str
    updated_at_utc: str
    executed_at_utc: str | None
    error_message: str


@dataclass(frozen=True)
class ActionExecutionRecord:
    id: str
    action_proposal_id: str
    created_at_utc: str
    executor_kind: str
    status: str
    result_json: str


@dataclass(frozen=True)
class ExportArtifactRecord:
    id: str
    session_id: str
    action_proposal_id: str | None
    file_path: str
    file_name: str
    mime_type: str
    size_bytes: int
    created_at_utc: str
    kind: str


@dataclass(frozen=True)
class TranscriptCorrectionProposalRecord:
    id: str
    session_id: str
    base_revision_id: str
    status: str
    scope_json: str
    strategy: str
    model_name: str
    before_snapshot_json: str
    after_snapshot_json: str
    diff_preview_json: str
    created_at_utc: str
    updated_at_utc: str
    applied_revision_id: str | None
    warnings_json: str


class SQLiteStore:
    """Small sqlite-backed app store for foundation work (sessions + jobs + settings)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._lock = Lock()

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            # WAL persists in the DB file header, so this one-time switch applies to
            # every later connection. It lets readers run concurrently with a writer
            # and, with synchronous=NORMAL (set per-connection), removes the fsync per
            # commit that otherwise blocks the voice WS handler on its ~10+ short writes.
            con.execute("PRAGMA journal_mode = WAL")
            self._create_core_tables(con)
            self._create_transcript_tables(con)
            self._create_chat_action_tables(con)
            self._create_indexes(con)
            con.commit()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        # synchronous and busy_timeout are per-connection (unlike journal_mode). NORMAL
        # is durable under WAL except on OS crash/power loss, an acceptable trade for a
        # local on-device DB; busy_timeout avoids spurious "database is locked" errors.
        con.execute("PRAGMA synchronous = NORMAL")
        con.execute("PRAGMA busy_timeout = 5000")
        return con

    @staticmethod
    def _create_core_tables(con: sqlite3.Connection) -> None:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS assistant_sessions (
                id TEXT PRIMARY KEY,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                title TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_language_hint TEXT NOT NULL DEFAULT 'auto',
                command_language_hint TEXT NOT NULL DEFAULT 'auto',
                status TEXT NOT NULL,
                last_error TEXT NOT NULL DEFAULT '',
                active_transcript_revision_id TEXT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS audio_assets (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                sample_rate_hz INTEGER NULL,
                channels INTEGER NULL,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                session_id TEXT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                created_at_utc TEXT NOT NULL,
                started_at_utc TEXT NULL,
                finished_at_utc TEXT NULL,
                input_json TEXT NOT NULL,
                output_json TEXT NOT NULL,
                error_message TEXT NOT NULL DEFAULT ''
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            )
            """
        )

    @staticmethod
    def _create_transcript_tables(con: sqlite3.Connection) -> None:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_revisions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                revision_number INTEGER NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_by TEXT NOT NULL,
                source TEXT NOT NULL,
                parent_revision_id TEXT NULL,
                full_text TEXT NOT NULL,
                language_detected TEXT NOT NULL DEFAULT '',
                diarization_used INTEGER NOT NULL,
                stt_model TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(parent_revision_id) REFERENCES transcript_revisions(id) ON DELETE SET NULL,
                UNIQUE(session_id, revision_number)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_speakers (
                id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL,
                speaker_key TEXT NOT NULL,
                display_name TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                FOREIGN KEY(revision_id) REFERENCES transcript_revisions(id) ON DELETE CASCADE,
                UNIQUE(revision_id, speaker_key)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_segments (
                id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL,
                segment_index INTEGER NOT NULL,
                speaker_id TEXT NULL,
                start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL,
                text TEXT NOT NULL,
                confidence REAL NULL,
                word_count INTEGER NOT NULL,
                embedding_vector_ref TEXT NULL,
                FOREIGN KEY(revision_id) REFERENCES transcript_revisions(id) ON DELETE CASCADE,
                FOREIGN KEY(speaker_id) REFERENCES transcript_speakers(id) ON DELETE SET NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_words (
                id TEXT PRIMARY KEY,
                segment_id TEXT NOT NULL,
                word_index INTEGER NOT NULL,
                start_ms INTEGER NULL,
                end_ms INTEGER NULL,
                word TEXT NOT NULL,
                confidence REAL NULL,
                FOREIGN KEY(segment_id) REFERENCES transcript_segments(id) ON DELETE CASCADE,
                UNIQUE(segment_id, word_index)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_edit_operations (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                revision_id_before TEXT NOT NULL,
                revision_id_after TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                actor TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(revision_id_before) REFERENCES transcript_revisions(id) ON DELETE CASCADE,
                FOREIGN KEY(revision_id_after) REFERENCES transcript_revisions(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_correction_proposals (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                base_revision_id TEXT NOT NULL,
                status TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                strategy TEXT NOT NULL,
                model_name TEXT NOT NULL DEFAULT '',
                before_snapshot_json TEXT NOT NULL,
                after_snapshot_json TEXT NOT NULL,
                diff_preview_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                applied_revision_id TEXT NULL,
                warnings_json TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(base_revision_id) REFERENCES transcript_revisions(id) ON DELETE CASCADE,
                FOREIGN KEY(applied_revision_id) REFERENCES transcript_revisions(id) ON DELETE SET NULL
            )
            """
        )

    @staticmethod
    def _create_chat_action_tables(con: sqlite3.Connection) -> None:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_threads (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT 'Chat',
                FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                transcript_revision_id TEXT NULL,
                role TEXT NOT NULL,
                content_markdown TEXT NOT NULL,
                content_plain_text TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                status TEXT NOT NULL,
                model_name TEXT NOT NULL DEFAULT '',
                created_at_utc TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                FOREIGN KEY(thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE,
                FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(transcript_revision_id) REFERENCES transcript_revisions(id) ON DELETE SET NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS message_citations (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                citation_index INTEGER NOT NULL,
                segment_id TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL,
                quote_excerpt TEXT NOT NULL,
                FOREIGN KEY(message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
                FOREIGN KEY(segment_id) REFERENCES transcript_segments(id) ON DELETE CASCADE,
                UNIQUE(message_id, citation_index)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS voice_commands (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                audio_asset_id TEXT NOT NULL,
                transcribed_text TEXT NOT NULL,
                edited_text TEXT NOT NULL DEFAULT '',
                send_mode TEXT NOT NULL,
                detected_language TEXT NOT NULL DEFAULT '',
                stt_model TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                sent_message_id TEXT NULL,
                FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE,
                FOREIGN KEY(audio_asset_id) REFERENCES audio_assets(id) ON DELETE CASCADE,
                FOREIGN KEY(sent_message_id) REFERENCES chat_messages(id) ON DELETE SET NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS action_proposals (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                requires_confirmation INTEGER NOT NULL DEFAULT 1,
                payload_json TEXT NOT NULL,
                preview_markdown TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                executed_at_utc TEXT NULL,
                error_message TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE,
                FOREIGN KEY(message_id) REFERENCES chat_messages(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS action_executions (
                id TEXT PRIMARY KEY,
                action_proposal_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                executor_kind TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL,
                FOREIGN KEY(action_proposal_id) REFERENCES action_proposals(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS export_artifacts (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                action_proposal_id TEXT NULL,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at_utc TEXT NOT NULL,
                kind TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(action_proposal_id) REFERENCES action_proposals(id) ON DELETE SET NULL
            )
            """
        )

    @staticmethod
    def _create_indexes(con: sqlite3.Connection) -> None:
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_assistant_sessions_updated_at
            ON assistant_sessions(updated_at_utc DESC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_assistant_sessions_status
            ON assistant_sessions(status)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audio_assets_session_kind
            ON audio_assets(session_id, kind)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transcript_segments_revision_index
            ON transcript_segments(revision_id, segment_index ASC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transcript_segments_revision_time
            ON transcript_segments(revision_id, start_ms ASC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transcript_words_segment_word_index
            ON transcript_words(segment_id, word_index ASC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transcript_edit_ops_session_created
            ON transcript_edit_operations(session_id, created_at_utc DESC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transcript_correction_proposals_session_created
            ON transcript_correction_proposals(session_id, created_at_utc DESC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transcript_correction_proposals_base_revision_created
            ON transcript_correction_proposals(base_revision_id, created_at_utc DESC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_threads_session_updated
            ON chat_threads(session_id, updated_at_utc DESC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_created
            ON chat_messages(thread_id, created_at_utc ASC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
            ON chat_messages(session_id, created_at_utc ASC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_voice_commands_session_created
            ON voice_commands(session_id, created_at_utc DESC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_action_proposals_session_status
            ON action_proposals(session_id, status)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_action_proposals_message
            ON action_proposals(message_id)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_export_artifacts_session_created
            ON export_artifacts(session_id, created_at_utc DESC)
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jobs_status_created
            ON jobs(status, created_at_utc DESC)
            """
        )

    def create_session(
        self,
        *,
        title: str,
        source_kind: str,
        source_name: str = "",
        source_language_hint: str = "auto",
        command_language_hint: str = "auto",
    ) -> SessionRecord:
        session_id = uuid4().hex
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO assistant_sessions (
                    id,
                    created_at_utc,
                    updated_at_utc,
                    title,
                    source_kind,
                    source_name,
                    source_language_hint,
                    command_language_hint,
                    status,
                    last_error,
                    active_transcript_revision_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', NULL)
                """,
                (
                    session_id,
                    now,
                    now,
                    title,
                    source_kind,
                    source_name,
                    source_language_hint,
                    command_language_hint,
                    "new",
                ),
            )
            row = con.execute(
                "SELECT * FROM assistant_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            con.commit()
        return self._row_to_session(row)

    def list_sessions(self, *, query: str = "", limit: int = 50) -> list[SessionRecord]:
        like_query = f"%{query.strip()}%" if query.strip() else None
        sql = """
            SELECT *
            FROM assistant_sessions
        """
        params: list[Any] = []
        if like_query:
            sql += " WHERE title LIKE ? OR source_name LIKE ? "
            params.extend([like_query, like_query])
        sql += " ORDER BY updated_at_utc DESC LIMIT ? "
        params.append(max(1, min(limit, 200)))
        with self._connect() as con:
            rows = con.execute(sql, params).fetchall()
        return [self._row_to_session(row) for row in rows]

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM assistant_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._row_to_session(row) if row else None

    def touch_session(self, session_id: str) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "UPDATE assistant_sessions SET updated_at_utc = ? WHERE id = ?",
                (_utc_now_iso(), session_id),
            )
            con.commit()

    def update_session_status(
        self,
        session_id: str,
        *,
        status: str,
        last_error: str | None = None,
        active_transcript_revision_id: str | None = None,
    ) -> None:
        with self._lock, self._connect() as con:
            existing = con.execute(
                "SELECT active_transcript_revision_id FROM assistant_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if existing is None:
                raise KeyError(session_id)
            next_revision_id = (
                existing["active_transcript_revision_id"]
                if active_transcript_revision_id is None
                else active_transcript_revision_id
            )
            next_last_error = "" if last_error is None else last_error
            con.execute(
                """
                UPDATE assistant_sessions
                SET updated_at_utc = ?,
                    status = ?,
                    last_error = ?,
                    active_transcript_revision_id = ?
                WHERE id = ?
                """,
                (_utc_now_iso(), status, next_last_error, next_revision_id, session_id),
            )
            con.commit()

    def update_session_title(self, session_id: str, title: str) -> SessionRecord:
        with self._lock, self._connect() as con:
            existing = con.execute(
                "SELECT id FROM assistant_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if existing is None:
                raise KeyError(session_id)
            con.execute(
                """
                UPDATE assistant_sessions
                SET title = ?, updated_at_utc = ?
                WHERE id = ?
                """,
                (title, _utc_now_iso(), session_id),
            )
            row = con.execute(
                "SELECT * FROM assistant_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            con.commit()
        return self._row_to_session(row)

    def delete_session_cascade(self, session_id: str) -> bool:
        with self._lock, self._connect() as con:
            con.execute("PRAGMA foreign_keys = ON")
            cursor = con.execute(
                "DELETE FROM assistant_sessions WHERE id = ?",
                (session_id,),
            )
            con.commit()
            return cursor.rowcount > 0

    def list_active_jobs_for_session(self, session_id: str) -> list[JobRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM jobs
                WHERE session_id = ? AND status IN ('queued', 'running')
                """,
                (session_id,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def create_audio_asset(
        self,
        *,
        session_id: str,
        kind: str,
        mime_type: str,
        file_path: str,
        duration_ms: int,
        sample_rate_hz: int | None = None,
        channels: int | None = None,
    ) -> AudioAssetRecord:
        audio_asset_id = uuid4().hex
        created_at_utc = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO audio_assets (
                    id,
                    session_id,
                    kind,
                    mime_type,
                    file_path,
                    duration_ms,
                    sample_rate_hz,
                    channels,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audio_asset_id,
                    session_id,
                    kind,
                    mime_type,
                    file_path,
                    int(duration_ms),
                    sample_rate_hz,
                    channels,
                    created_at_utc,
                ),
            )
            con.execute(
                "UPDATE assistant_sessions SET updated_at_utc = ? WHERE id = ?",
                (created_at_utc, session_id),
            )
            row = con.execute(
                "SELECT * FROM audio_assets WHERE id = ?", (audio_asset_id,)
            ).fetchone()
            con.commit()
        return self._row_to_audio_asset(row)

    def get_audio_asset(self, audio_asset_id: str) -> AudioAssetRecord | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM audio_assets WHERE id = ?", (audio_asset_id,)
            ).fetchone()
        return self._row_to_audio_asset(row) if row else None

    def get_audio_asset_for_session(
        self,
        session_id: str,
        kind: str = "meeting_audio",
    ) -> AudioAssetRecord | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM audio_assets WHERE session_id = ? AND kind = ?"
                " ORDER BY created_at_utc DESC LIMIT 1",
                (session_id, kind),
            ).fetchone()
        return self._row_to_audio_asset(row) if row else None

    def get_transcript_revision(self, revision_id: str) -> TranscriptRevisionRecord | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM transcript_revisions WHERE id = ?",
                (revision_id,),
            ).fetchone()
        return self._row_to_transcript_revision(row) if row else None

    def get_latest_transcript_revision_for_session(
        self,
        session_id: str,
    ) -> TranscriptRevisionRecord | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT *
                FROM transcript_revisions
                WHERE session_id = ?
                ORDER BY revision_number DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return self._row_to_transcript_revision(row) if row else None

    def list_transcript_revisions(self, session_id: str) -> list[TranscriptRevisionRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT *
                FROM transcript_revisions
                WHERE session_id = ?
                ORDER BY revision_number DESC
                """,
                (session_id,),
            ).fetchall()
        return [self._row_to_transcript_revision(row) for row in rows]

    def list_transcript_speakers(self, revision_id: str) -> list[TranscriptSpeakerRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT *
                FROM transcript_speakers
                WHERE revision_id = ?
                ORDER BY sort_order ASC, speaker_key ASC
                """,
                (revision_id,),
            ).fetchall()
        return [self._row_to_transcript_speaker(row) for row in rows]

    def list_transcript_segments(self, revision_id: str) -> list[TranscriptSegmentRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT *
                FROM transcript_segments
                WHERE revision_id = ?
                ORDER BY segment_index ASC
                """,
                (revision_id,),
            ).fetchall()
        return [self._row_to_transcript_segment(row) for row in rows]

    def list_transcript_words_for_revision(self, revision_id: str) -> list[TranscriptWordRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT w.*
                FROM transcript_words w
                INNER JOIN transcript_segments s ON s.id = w.segment_id
                WHERE s.revision_id = ?
                ORDER BY s.segment_index ASC, w.word_index ASC
                """,
                (revision_id,),
            ).fetchall()
        return [self._row_to_transcript_word(row) for row in rows]

    def get_transcript_speaker(self, speaker_id: str) -> TranscriptSpeakerRecord | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM transcript_speakers WHERE id = ?",
                (speaker_id,),
            ).fetchone()
        return self._row_to_transcript_speaker(row) if row else None

    def get_transcript_segment(self, segment_id: str) -> TranscriptSegmentRecord | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM transcript_segments WHERE id = ?",
                (segment_id,),
            ).fetchone()
        return self._row_to_transcript_segment(row) if row else None

    def create_transcript_edit_operation(
        self,
        *,
        session_id: str,
        revision_id_before: str,
        revision_id_after: str,
        actor: str,
        operation_type: str,
        payload: dict[str, Any],
    ) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO transcript_edit_operations (
                    id,
                    session_id,
                    revision_id_before,
                    revision_id_after,
                    created_at_utc,
                    actor,
                    operation_type,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex,
                    session_id,
                    revision_id_before,
                    revision_id_after,
                    _utc_now_iso(),
                    actor,
                    operation_type,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            con.commit()

    def _clone_transcript_revision_with_overrides(
        self,
        *,
        session_id: str,
        base_revision: TranscriptRevisionRecord,
        created_by: str,
        source: str,
        operation_type: str,
        operation_payload: dict[str, Any],
        segment_text_overrides: dict[str, str] | None = None,
        speaker_name_overrides: dict[str, str] | None = None,
        reset_embeddings: bool = True,
    ) -> TranscriptRevisionCreateResult:
        latest_revision = self.get_latest_transcript_revision_for_session(session_id)
        if latest_revision is None or latest_revision.id != base_revision.id:
            raise ValueError("Edits are only allowed on the latest transcript revision.")

        base_speakers = self.list_transcript_speakers(base_revision.id)
        base_segments = self.list_transcript_segments(base_revision.id)
        base_words = self.list_transcript_words_for_revision(base_revision.id)
        speaker_by_id = {speaker.id: speaker for speaker in base_speakers}
        words_by_segment_id: dict[str, list[TranscriptWordRecord]] = {}
        for word in base_words:
            words_by_segment_id.setdefault(word.segment_id, []).append(word)

        segment_text_overrides = segment_text_overrides or {}
        speaker_name_overrides = speaker_name_overrides or {}

        next_speakers = [
            TranscriptSpeakerInput(
                speaker_key=speaker.speaker_key,
                display_name=speaker_name_overrides.get(speaker.id, speaker.display_name),
                sort_order=speaker.sort_order,
            )
            for speaker in base_speakers
        ]

        next_segments: list[TranscriptSegmentInput] = []
        ordered_segments = sorted(base_segments, key=lambda item: item.segment_index)
        for segment in ordered_segments:
            next_text = segment_text_overrides.get(segment.id, segment.text)
            current_words = words_by_segment_id.get(segment.id, [])
            preserve_words = segment.id not in segment_text_overrides
            speaker_key = None
            if segment.speaker_id is not None and segment.speaker_id in speaker_by_id:
                speaker_key = speaker_by_id[segment.speaker_id].speaker_key

            words_inputs: tuple[TranscriptWordInput, ...] = ()
            if preserve_words and current_words:
                words_inputs = tuple(
                    TranscriptWordInput(
                        word_index=word.word_index,
                        word=word.word,
                        start_ms=word.start_ms,
                        end_ms=word.end_ms,
                        confidence=word.confidence,
                    )
                    for word in sorted(current_words, key=lambda item: item.word_index)
                )

            if preserve_words:
                next_word_count = segment.word_count
            else:
                next_word_count = len(next_text.split()) if next_text.strip() else 0

            next_segments.append(
                TranscriptSegmentInput(
                    segment_index=segment.segment_index,
                    speaker_key=speaker_key,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=next_text,
                    confidence=segment.confidence,
                    word_count=next_word_count,
                    embedding_vector_ref=None if reset_embeddings else segment.embedding_vector_ref,
                    words=words_inputs,
                )
            )

        full_text = "\n".join(segment.text for segment in next_segments)
        try:
            warnings = json.loads(base_revision.warnings_json)
        except Exception:
            warnings = []
        if not isinstance(warnings, list):
            warnings = []

        created = self.create_transcript_revision(
            session_id=session_id,
            created_by=created_by,
            source=source,
            full_text=full_text,
            language_detected=base_revision.language_detected,
            diarization_used=base_revision.diarization_used,
            stt_model=base_revision.stt_model,
            warnings=tuple(str(item) for item in warnings),
            speakers=tuple(next_speakers),
            segments=tuple(next_segments),
            parent_revision_id=base_revision.id,
            set_session_status="ready",
        )
        self.create_transcript_edit_operation(
            session_id=session_id,
            revision_id_before=base_revision.id,
            revision_id_after=created.revision.id,
            actor=created_by,
            operation_type=operation_type,
            payload=operation_payload,
        )
        return created

    def edit_transcript_segment_text(
        self,
        *,
        session_id: str,
        segment_id: str,
        new_text: str,
        actor: str = "user",
    ) -> TranscriptRevisionCreateResult:
        segment = self.get_transcript_segment(segment_id)
        if segment is None:
            raise KeyError("segment_not_found")
        base_revision = self.get_transcript_revision(segment.revision_id)
        if base_revision is None or base_revision.session_id != session_id:
            raise KeyError("segment_not_found")

        cleaned_text = new_text.strip()
        if not cleaned_text:
            raise ValueError("Segment text cannot be empty.")
        if cleaned_text == segment.text:
            raise ValueError("No text change detected for this segment.")

        return self._clone_transcript_revision_with_overrides(
            session_id=session_id,
            base_revision=base_revision,
            created_by=actor,
            source="manual_segment_edit",
            operation_type="segment_text_edit",
            operation_payload={
                "segment_id": segment.id,
                "segment_index": segment.segment_index,
                "old_text": segment.text,
                "new_text": cleaned_text,
            },
            segment_text_overrides={segment.id: cleaned_text},
        )

    def rename_transcript_speaker(
        self,
        *,
        session_id: str,
        speaker_id: str,
        display_name: str,
        actor: str = "user",
    ) -> TranscriptRevisionCreateResult:
        speaker = self.get_transcript_speaker(speaker_id)
        if speaker is None:
            raise KeyError("speaker_not_found")
        base_revision = self.get_transcript_revision(speaker.revision_id)
        if base_revision is None or base_revision.session_id != session_id:
            raise KeyError("speaker_not_found")

        cleaned_name = display_name.strip()
        if not cleaned_name:
            raise ValueError("Speaker display name cannot be empty.")
        if cleaned_name == speaker.display_name:
            raise ValueError("No name change detected for this speaker.")

        return self._clone_transcript_revision_with_overrides(
            session_id=session_id,
            base_revision=base_revision,
            created_by=actor,
            source="speaker_rename",
            operation_type="speaker_rename",
            operation_payload={
                "speaker_id": speaker.id,
                "speaker_key": speaker.speaker_key,
                "old_display_name": speaker.display_name,
                "new_display_name": cleaned_name,
            },
            speaker_name_overrides={speaker.id: cleaned_name},
        )

    def create_transcript_revision_from_text_overrides(
        self,
        *,
        session_id: str,
        base_revision_id: str,
        segment_text_overrides: dict[str, str],
        actor: str,
        source: str,
        operation_type: str,
        operation_payload: dict[str, Any],
    ) -> TranscriptRevisionCreateResult:
        if not segment_text_overrides:
            raise ValueError("No segment text overrides supplied.")
        base_revision = self.get_transcript_revision(base_revision_id)
        if base_revision is None or base_revision.session_id != session_id:
            raise KeyError("base_revision_not_found")
        cleaned: dict[str, str] = {}
        for segment_id, value in segment_text_overrides.items():
            next_text = value.strip()
            if not next_text:
                raise ValueError("Corrected segment text cannot be empty.")
            cleaned[segment_id] = next_text
        return self._clone_transcript_revision_with_overrides(
            session_id=session_id,
            base_revision=base_revision,
            created_by=actor,
            source=source,
            operation_type=operation_type,
            operation_payload=operation_payload,
            segment_text_overrides=cleaned,
        )

    def create_transcript_correction_proposal(
        self,
        *,
        session_id: str,
        base_revision_id: str,
        status: str,
        scope: dict[str, Any],
        strategy: str,
        model_name: str,
        before_snapshot: dict[str, Any],
        after_snapshot: dict[str, Any],
        diff_preview: dict[str, Any],
        warnings: list[str] | tuple[str, ...] = (),
    ) -> TranscriptCorrectionProposalRecord:
        proposal_id = uuid4().hex
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO transcript_correction_proposals (
                    id,
                    session_id,
                    base_revision_id,
                    status,
                    scope_json,
                    strategy,
                    model_name,
                    before_snapshot_json,
                    after_snapshot_json,
                    diff_preview_json,
                    created_at_utc,
                    updated_at_utc,
                    applied_revision_id,
                    warnings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    proposal_id,
                    session_id,
                    base_revision_id,
                    status,
                    json.dumps(scope, ensure_ascii=False),
                    strategy,
                    model_name,
                    json.dumps(before_snapshot, ensure_ascii=False),
                    json.dumps(after_snapshot, ensure_ascii=False),
                    json.dumps(diff_preview, ensure_ascii=False),
                    now,
                    now,
                    json.dumps(list(warnings), ensure_ascii=False),
                ),
            )
            con.execute(
                "UPDATE assistant_sessions SET updated_at_utc = ? WHERE id = ?",
                (now, session_id),
            )
            row = con.execute(
                "SELECT * FROM transcript_correction_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
            con.commit()
        return self._row_to_transcript_correction_proposal(row)

    def get_transcript_correction_proposal(
        self,
        proposal_id: str,
    ) -> TranscriptCorrectionProposalRecord | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM transcript_correction_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
        return self._row_to_transcript_correction_proposal(row) if row else None

    def list_transcript_correction_proposals(
        self,
        session_id: str,
    ) -> list[TranscriptCorrectionProposalRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM transcript_correction_proposals
                WHERE session_id = ?
                ORDER BY created_at_utc DESC
                """,
                (session_id,),
            ).fetchall()
        return [self._row_to_transcript_correction_proposal(row) for row in rows]

    def update_transcript_correction_proposal(
        self,
        proposal_id: str,
        *,
        status: str | None = None,
        applied_revision_id: str | None = None,
        warnings: list[str] | tuple[str, ...] | None = None,
    ) -> TranscriptCorrectionProposalRecord:
        current = self.get_transcript_correction_proposal(proposal_id)
        if current is None:
            raise KeyError(proposal_id)
        next_status = current.status if status is None else status
        next_applied_revision_id = (
            current.applied_revision_id if applied_revision_id is None else applied_revision_id
        )
        next_warnings_json = (
            current.warnings_json
            if warnings is None
            else json.dumps(list(warnings), ensure_ascii=False)
        )
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                UPDATE transcript_correction_proposals
                SET status = ?,
                    updated_at_utc = ?,
                    applied_revision_id = ?,
                    warnings_json = ?
                WHERE id = ?
                """,
                (next_status, now, next_applied_revision_id, next_warnings_json, proposal_id),
            )
            row = con.execute(
                "SELECT * FROM transcript_correction_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
            con.commit()
        return self._row_to_transcript_correction_proposal(row)

    def create_transcript_revision(
        self,
        *,
        session_id: str,
        created_by: str,
        source: str,
        full_text: str,
        language_detected: str = "",
        diarization_used: bool = False,
        stt_model: str = "",
        warnings: tuple[str, ...] | list[str] = (),
        speakers: tuple[TranscriptSpeakerInput, ...] | list[TranscriptSpeakerInput] = (),
        segments: tuple[TranscriptSegmentInput, ...] | list[TranscriptSegmentInput] = (),
        parent_revision_id: str | None = None,
        set_session_status: str = "ready",
    ) -> TranscriptRevisionCreateResult:
        now = _utc_now_iso()
        revision_id = uuid4().hex
        with self._lock, self._connect() as con:
            max_revision = con.execute(
                "SELECT COALESCE(MAX(revision_number), 0) FROM transcript_revisions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            revision_number = int(max_revision[0]) + 1 if max_revision is not None else 1
            warnings_json = json.dumps(list(warnings), ensure_ascii=False)
            con.execute(
                """
                INSERT INTO transcript_revisions (
                    id,
                    session_id,
                    revision_number,
                    created_at_utc,
                    created_by,
                    source,
                    parent_revision_id,
                    full_text,
                    language_detected,
                    diarization_used,
                    stt_model,
                    warnings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    session_id,
                    revision_number,
                    now,
                    created_by,
                    source,
                    parent_revision_id,
                    full_text,
                    language_detected,
                    int(diarization_used),
                    stt_model,
                    warnings_json,
                ),
            )

            speaker_ids_by_key: dict[str, str] = {}
            for speaker in sorted(list(speakers), key=lambda s: (s.sort_order, s.speaker_key)):
                speaker_id = uuid4().hex
                con.execute(
                    """
                    INSERT INTO transcript_speakers (
                        id,
                        revision_id,
                        speaker_key,
                        display_name,
                        sort_order
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        speaker_id,
                        revision_id,
                        speaker.speaker_key,
                        speaker.display_name,
                        int(speaker.sort_order),
                    ),
                )
                speaker_ids_by_key[speaker.speaker_key] = speaker_id

            segment_ids: list[str] = []
            for segment in sorted(list(segments), key=lambda s: s.segment_index):
                segment_id = uuid4().hex
                segment_ids.append(segment_id)
                speaker_id = (
                    speaker_ids_by_key.get(segment.speaker_key)
                    if segment.speaker_key is not None
                    else None
                )
                con.execute(
                    """
                    INSERT INTO transcript_segments (
                        id,
                        revision_id,
                        segment_index,
                        speaker_id,
                        start_ms,
                        end_ms,
                        text,
                        confidence,
                        word_count,
                        embedding_vector_ref
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        segment_id,
                        revision_id,
                        int(segment.segment_index),
                        speaker_id,
                        int(segment.start_ms),
                        int(segment.end_ms),
                        segment.text,
                        segment.confidence,
                        int(segment.word_count),
                        segment.embedding_vector_ref,
                    ),
                )
                for word in sorted(list(segment.words), key=lambda w: w.word_index):
                    con.execute(
                        """
                        INSERT INTO transcript_words (
                            id,
                            segment_id,
                            word_index,
                            start_ms,
                            end_ms,
                            word,
                            confidence
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            uuid4().hex,
                            segment_id,
                            int(word.word_index),
                            word.start_ms,
                            word.end_ms,
                            word.word,
                            word.confidence,
                        ),
                    )

            con.execute(
                """
                UPDATE assistant_sessions
                SET updated_at_utc = ?,
                    status = ?,
                    last_error = '',
                    active_transcript_revision_id = ?
                WHERE id = ?
                """,
                (now, set_session_status, revision_id, session_id),
            )
            row = con.execute(
                "SELECT * FROM transcript_revisions WHERE id = ?",
                (revision_id,),
            ).fetchone()
            con.commit()

        return TranscriptRevisionCreateResult(
            revision=self._row_to_transcript_revision(row),
            speaker_ids_by_key=speaker_ids_by_key,
            segment_ids=tuple(segment_ids),
        )

    def get_or_create_chat_thread(
        self, *, session_id: str, title: str = "Chat"
    ) -> ChatThreadRecord:
        existing = self.get_chat_thread_for_session(session_id)
        if existing is not None:
            return existing
        thread_id = uuid4().hex
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO chat_threads (id, session_id, created_at_utc, updated_at_utc, title)
                VALUES (?, ?, ?, ?, ?)
                """,
                (thread_id, session_id, now, now, title),
            )
            con.execute(
                "UPDATE assistant_sessions SET updated_at_utc = ? WHERE id = ?",
                (now, session_id),
            )
            row = con.execute("SELECT * FROM chat_threads WHERE id = ?", (thread_id,)).fetchone()
            con.commit()
        return self._row_to_chat_thread(row)

    def get_chat_thread_for_session(self, session_id: str) -> ChatThreadRecord | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT * FROM chat_threads
                WHERE session_id = ?
                ORDER BY created_at_utc ASC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return self._row_to_chat_thread(row) if row else None

    def get_chat_thread(self, thread_id: str) -> ChatThreadRecord | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM chat_threads WHERE id = ?", (thread_id,)).fetchone()
        return self._row_to_chat_thread(row) if row else None

    def _touch_chat_thread_tx(self, con: sqlite3.Connection, thread_id: str, now: str) -> None:
        row = con.execute(
            "SELECT session_id FROM chat_threads WHERE id = ?", (thread_id,)
        ).fetchone()
        if row is None:
            raise KeyError(thread_id)
        con.execute(
            "UPDATE chat_threads SET updated_at_utc = ? WHERE id = ?",
            (now, thread_id),
        )
        con.execute(
            "UPDATE assistant_sessions SET updated_at_utc = ? WHERE id = ?",
            (now, row["session_id"]),
        )

    def create_chat_message(
        self,
        *,
        thread_id: str,
        session_id: str,
        transcript_revision_id: str | None,
        role: str,
        content_markdown: str,
        content_plain_text: str,
        source_kind: str,
        status: str = "completed",
        model_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessageRecord:
        message_id = uuid4().hex
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO chat_messages (
                    id,
                    thread_id,
                    session_id,
                    transcript_revision_id,
                    role,
                    content_markdown,
                    content_plain_text,
                    source_kind,
                    status,
                    model_name,
                    created_at_utc,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    thread_id,
                    session_id,
                    transcript_revision_id,
                    role,
                    content_markdown,
                    content_plain_text,
                    source_kind,
                    status,
                    model_name,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            self._touch_chat_thread_tx(con, thread_id, now)
            row = con.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
            con.commit()
        return self._row_to_chat_message(row)

    def get_chat_message(self, message_id: str) -> ChatMessageRecord | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        return self._row_to_chat_message(row) if row else None

    def update_chat_message(
        self,
        message_id: str,
        *,
        content_markdown: str | None = None,
        content_plain_text: str | None = None,
        status: str | None = None,
        model_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessageRecord:
        current = self.get_chat_message(message_id)
        if current is None:
            raise KeyError(message_id)
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                UPDATE chat_messages
                SET content_markdown = ?,
                    content_plain_text = ?,
                    status = ?,
                    model_name = ?,
                    metadata_json = ?
                WHERE id = ?
                """,
                (
                    current.content_markdown if content_markdown is None else content_markdown,
                    current.content_plain_text
                    if content_plain_text is None
                    else content_plain_text,
                    current.status if status is None else status,
                    current.model_name if model_name is None else model_name,
                    current.metadata_json
                    if metadata is None
                    else json.dumps(metadata, ensure_ascii=False),
                    message_id,
                ),
            )
            self._touch_chat_thread_tx(con, current.thread_id, now)
            row = con.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
            con.commit()
        return self._row_to_chat_message(row)

    def list_chat_messages(self, thread_id: str) -> list[ChatMessageRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM chat_messages
                WHERE thread_id = ?
                ORDER BY created_at_utc ASC, id ASC
                """,
                (thread_id,),
            ).fetchall()
        return [self._row_to_chat_message(row) for row in rows]

    def create_message_citations(
        self,
        *,
        message_id: str,
        citations: list[MessageCitationInput] | tuple[MessageCitationInput, ...],
    ) -> list[MessageCitationRecord]:
        with self._lock, self._connect() as con:
            for citation in sorted(list(citations), key=lambda item: item.citation_index):
                con.execute(
                    """
                    INSERT INTO message_citations (
                        id,
                        message_id,
                        citation_index,
                        segment_id,
                        start_ms,
                        end_ms,
                        quote_excerpt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid4().hex,
                        message_id,
                        int(citation.citation_index),
                        citation.segment_id,
                        int(citation.start_ms),
                        int(citation.end_ms),
                        citation.quote_excerpt,
                    ),
                )
            rows = con.execute(
                """
                SELECT * FROM message_citations
                WHERE message_id = ?
                ORDER BY citation_index ASC
                """,
                (message_id,),
            ).fetchall()
            con.commit()
        return [self._row_to_message_citation(row) for row in rows]

    def list_message_citations(self, message_id: str) -> list[MessageCitationRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM message_citations
                WHERE message_id = ?
                ORDER BY citation_index ASC
                """,
                (message_id,),
            ).fetchall()
        return [self._row_to_message_citation(row) for row in rows]

    def create_voice_command(
        self,
        *,
        session_id: str,
        thread_id: str,
        audio_asset_id: str,
        transcribed_text: str,
        edited_text: str = "",
        send_mode: str,
        detected_language: str = "",
        stt_model: str = "",
        sent_message_id: str | None = None,
    ) -> VoiceCommandRecord:
        voice_command_id = uuid4().hex
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO voice_commands (
                    id,
                    session_id,
                    thread_id,
                    audio_asset_id,
                    transcribed_text,
                    edited_text,
                    send_mode,
                    detected_language,
                    stt_model,
                    created_at_utc,
                    sent_message_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    voice_command_id,
                    session_id,
                    thread_id,
                    audio_asset_id,
                    transcribed_text,
                    edited_text,
                    send_mode,
                    detected_language,
                    stt_model,
                    now,
                    sent_message_id,
                ),
            )
            con.execute(
                "UPDATE assistant_sessions SET updated_at_utc = ? WHERE id = ?",
                (now, session_id),
            )
            row = con.execute(
                "SELECT * FROM voice_commands WHERE id = ?", (voice_command_id,)
            ).fetchone()
            con.commit()
        return self._row_to_voice_command(row)

    def list_voice_commands(self, session_id: str) -> list[VoiceCommandRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM voice_commands
                WHERE session_id = ?
                ORDER BY created_at_utc DESC
                """,
                (session_id,),
            ).fetchall()
        return [self._row_to_voice_command(row) for row in rows]

    def create_action_proposal(
        self,
        *,
        session_id: str,
        thread_id: str,
        message_id: str,
        action_type: str,
        title: str,
        payload: dict[str, Any],
        preview_markdown: str,
        status: str = "pending",
        requires_confirmation: bool = True,
    ) -> ActionProposalRecord:
        action_id = uuid4().hex
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO action_proposals (
                    id,
                    session_id,
                    thread_id,
                    message_id,
                    action_type,
                    title,
                    status,
                    requires_confirmation,
                    payload_json,
                    preview_markdown,
                    created_at_utc,
                    updated_at_utc,
                    executed_at_utc,
                    error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, '')
                """,
                (
                    action_id,
                    session_id,
                    thread_id,
                    message_id,
                    action_type,
                    title,
                    status,
                    int(requires_confirmation),
                    json.dumps(payload, ensure_ascii=False),
                    preview_markdown,
                    now,
                    now,
                ),
            )
            self._touch_chat_thread_tx(con, thread_id, now)
            row = con.execute(
                "SELECT * FROM action_proposals WHERE id = ?", (action_id,)
            ).fetchone()
            con.commit()
        return self._row_to_action_proposal(row)

    def get_action_proposal(self, action_id: str) -> ActionProposalRecord | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM action_proposals WHERE id = ?", (action_id,)
            ).fetchone()
        return self._row_to_action_proposal(row) if row else None

    def list_action_proposals(
        self, *, session_id: str, status: str | None = None
    ) -> list[ActionProposalRecord]:
        with self._connect() as con:
            if status is None:
                rows = con.execute(
                    """
                    SELECT * FROM action_proposals
                    WHERE session_id = ?
                    ORDER BY created_at_utc ASC
                    """,
                    (session_id,),
                ).fetchall()
            else:
                rows = con.execute(
                    """
                    SELECT * FROM action_proposals
                    WHERE session_id = ? AND status = ?
                    ORDER BY created_at_utc ASC
                    """,
                    (session_id, status),
                ).fetchall()
        return [self._row_to_action_proposal(row) for row in rows]

    def list_action_proposals_for_message(self, message_id: str) -> list[ActionProposalRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM action_proposals
                WHERE message_id = ?
                ORDER BY created_at_utc ASC
                """,
                (message_id,),
            ).fetchall()
        return [self._row_to_action_proposal(row) for row in rows]

    def update_action_proposal(
        self,
        action_id: str,
        *,
        status: str | None = None,
        error_message: str | None = None,
        executed: bool = False,
    ) -> ActionProposalRecord:
        current = self.get_action_proposal(action_id)
        if current is None:
            raise KeyError(action_id)
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                UPDATE action_proposals
                SET status = ?,
                    updated_at_utc = ?,
                    executed_at_utc = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    current.status if status is None else status,
                    now,
                    now if executed else current.executed_at_utc,
                    current.error_message if error_message is None else error_message,
                    action_id,
                ),
            )
            row = con.execute(
                "SELECT * FROM action_proposals WHERE id = ?", (action_id,)
            ).fetchone()
            self._touch_chat_thread_tx(con, current.thread_id, now)
            con.commit()
        return self._row_to_action_proposal(row)

    def create_action_execution(
        self,
        *,
        action_proposal_id: str,
        executor_kind: str,
        status: str,
        result: dict[str, Any],
    ) -> ActionExecutionRecord:
        execution_id = uuid4().hex
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO action_executions (
                    id,
                    action_proposal_id,
                    created_at_utc,
                    executor_kind,
                    status,
                    result_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    action_proposal_id,
                    now,
                    executor_kind,
                    status,
                    json.dumps(result, ensure_ascii=False),
                ),
            )
            row = con.execute(
                "SELECT * FROM action_executions WHERE id = ?", (execution_id,)
            ).fetchone()
            con.commit()
        return self._row_to_action_execution(row)

    def list_action_executions(self, action_proposal_id: str) -> list[ActionExecutionRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM action_executions
                WHERE action_proposal_id = ?
                ORDER BY created_at_utc ASC
                """,
                (action_proposal_id,),
            ).fetchall()
        return [self._row_to_action_execution(row) for row in rows]

    def create_export_artifact(
        self,
        *,
        session_id: str,
        action_proposal_id: str | None,
        file_path: str,
        file_name: str,
        mime_type: str,
        size_bytes: int,
        kind: str,
    ) -> ExportArtifactRecord:
        artifact_id = uuid4().hex
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO export_artifacts (
                    id,
                    session_id,
                    action_proposal_id,
                    file_path,
                    file_name,
                    mime_type,
                    size_bytes,
                    created_at_utc,
                    kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    session_id,
                    action_proposal_id,
                    file_path,
                    file_name,
                    mime_type,
                    int(size_bytes),
                    now,
                    kind,
                ),
            )
            con.execute(
                "UPDATE assistant_sessions SET updated_at_utc = ? WHERE id = ?",
                (now, session_id),
            )
            row = con.execute(
                "SELECT * FROM export_artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
            con.commit()
        return self._row_to_export_artifact(row)

    def list_export_artifacts(self, session_id: str) -> list[ExportArtifactRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM export_artifacts
                WHERE session_id = ?
                ORDER BY created_at_utc DESC
                """,
                (session_id,),
            ).fetchall()
        return [self._row_to_export_artifact(row) for row in rows]

    def list_export_artifacts_for_action(
        self, action_proposal_id: str
    ) -> list[ExportArtifactRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM export_artifacts
                WHERE action_proposal_id = ?
                ORDER BY created_at_utc ASC
                """,
                (action_proposal_id,),
            ).fetchall()
        return [self._row_to_export_artifact(row) for row in rows]

    def get_export_artifact(self, artifact_id: str) -> ExportArtifactRecord | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM export_artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
        return self._row_to_export_artifact(row) if row else None

    def get_app_setting(self, key: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT value_json FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        try:
            parsed = json.loads(row["value_json"])
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def set_app_setting(self, key: str, value: dict[str, Any]) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO app_settings (key, value_json, updated_at_utc)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (key, json.dumps(value, ensure_ascii=False), _utc_now_iso()),
            )
            con.commit()

    def create_job(
        self,
        *,
        job_type: str,
        session_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
    ) -> JobRecord:
        job_id = uuid4().hex
        now = _utc_now_iso()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO jobs (
                    id, session_id, job_type, status, progress, created_at_utc,
                    started_at_utc, finished_at_utc, input_json, output_json, error_message
                ) VALUES (?, ?, ?, 'queued', 0, ?, NULL, NULL, ?, '{}', '')
                """,
                (
                    job_id,
                    session_id,
                    job_type,
                    now,
                    json.dumps(input_payload or {}, ensure_ascii=False),
                ),
            )
            row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            con.commit()
        return self._row_to_job(row)

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        output_payload: dict[str, Any] | None = None,
        error_message: str | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> JobRecord:
        current = self.get_job(job_id)
        if current is None:
            raise KeyError(job_id)
        next_status = status or current.status
        next_progress = current.progress if progress is None else progress
        next_output = current.output_json
        if output_payload is not None:
            next_output = json.dumps(output_payload, ensure_ascii=False)
        next_error = current.error_message if error_message is None else error_message
        next_started = current.started_at_utc
        next_finished = current.finished_at_utc
        now = _utc_now_iso()
        if started and not next_started:
            next_started = now
        if finished:
            next_finished = now
        with self._lock, self._connect() as con:
            con.execute(
                """
                UPDATE jobs
                SET status = ?,
                    progress = ?,
                    started_at_utc = ?,
                    finished_at_utc = ?,
                    output_json = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    float(next_progress),
                    next_started,
                    next_finished,
                    next_output,
                    next_error,
                    job_id,
                ),
            )
            row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            con.commit()
        return self._row_to_job(row)

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
            title=row["title"],
            source_kind=row["source_kind"],
            source_name=row["source_name"],
            source_language_hint=row["source_language_hint"],
            command_language_hint=row["command_language_hint"],
            status=row["status"],
            last_error=row["last_error"],
            active_transcript_revision_id=row["active_transcript_revision_id"],
        )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            session_id=row["session_id"],
            job_type=row["job_type"],
            status=row["status"],
            progress=float(row["progress"]),
            created_at_utc=row["created_at_utc"],
            started_at_utc=row["started_at_utc"],
            finished_at_utc=row["finished_at_utc"],
            input_json=row["input_json"],
            output_json=row["output_json"],
            error_message=row["error_message"],
        )

    @staticmethod
    def _row_to_audio_asset(row: sqlite3.Row) -> AudioAssetRecord:
        return AudioAssetRecord(
            id=row["id"],
            session_id=row["session_id"],
            kind=row["kind"],
            mime_type=row["mime_type"],
            file_path=row["file_path"],
            duration_ms=int(row["duration_ms"]),
            sample_rate_hz=row["sample_rate_hz"],
            channels=row["channels"],
            created_at_utc=row["created_at_utc"],
        )

    @staticmethod
    def _row_to_transcript_revision(row: sqlite3.Row) -> TranscriptRevisionRecord:
        return TranscriptRevisionRecord(
            id=row["id"],
            session_id=row["session_id"],
            revision_number=int(row["revision_number"]),
            created_at_utc=row["created_at_utc"],
            created_by=row["created_by"],
            source=row["source"],
            parent_revision_id=row["parent_revision_id"],
            full_text=row["full_text"],
            language_detected=row["language_detected"],
            diarization_used=bool(row["diarization_used"]),
            stt_model=row["stt_model"],
            warnings_json=row["warnings_json"],
        )

    @staticmethod
    def _row_to_transcript_speaker(row: sqlite3.Row) -> TranscriptSpeakerRecord:
        return TranscriptSpeakerRecord(
            id=row["id"],
            revision_id=row["revision_id"],
            speaker_key=row["speaker_key"],
            display_name=row["display_name"],
            sort_order=int(row["sort_order"]),
        )

    @staticmethod
    def _row_to_transcript_segment(row: sqlite3.Row) -> TranscriptSegmentRecord:
        confidence = row["confidence"]
        return TranscriptSegmentRecord(
            id=row["id"],
            revision_id=row["revision_id"],
            segment_index=int(row["segment_index"]),
            speaker_id=row["speaker_id"],
            start_ms=int(row["start_ms"]),
            end_ms=int(row["end_ms"]),
            text=row["text"],
            confidence=float(confidence) if confidence is not None else None,
            word_count=int(row["word_count"]),
            embedding_vector_ref=row["embedding_vector_ref"],
        )

    @staticmethod
    def _row_to_transcript_word(row: sqlite3.Row) -> TranscriptWordRecord:
        confidence = row["confidence"]
        return TranscriptWordRecord(
            id=row["id"],
            segment_id=row["segment_id"],
            word_index=int(row["word_index"]),
            start_ms=int(row["start_ms"]) if row["start_ms"] is not None else None,
            end_ms=int(row["end_ms"]) if row["end_ms"] is not None else None,
            word=row["word"],
            confidence=float(confidence) if confidence is not None else None,
        )

    @staticmethod
    def _row_to_chat_thread(row: sqlite3.Row) -> ChatThreadRecord:
        return ChatThreadRecord(
            id=row["id"],
            session_id=row["session_id"],
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
            title=row["title"],
        )

    @staticmethod
    def _row_to_chat_message(row: sqlite3.Row) -> ChatMessageRecord:
        return ChatMessageRecord(
            id=row["id"],
            thread_id=row["thread_id"],
            session_id=row["session_id"],
            transcript_revision_id=row["transcript_revision_id"],
            role=row["role"],
            content_markdown=row["content_markdown"],
            content_plain_text=row["content_plain_text"],
            source_kind=row["source_kind"],
            status=row["status"],
            model_name=row["model_name"],
            created_at_utc=row["created_at_utc"],
            metadata_json=row["metadata_json"],
        )

    @staticmethod
    def _row_to_message_citation(row: sqlite3.Row) -> MessageCitationRecord:
        return MessageCitationRecord(
            id=row["id"],
            message_id=row["message_id"],
            citation_index=int(row["citation_index"]),
            segment_id=row["segment_id"],
            start_ms=int(row["start_ms"]),
            end_ms=int(row["end_ms"]),
            quote_excerpt=row["quote_excerpt"],
        )

    @staticmethod
    def _row_to_voice_command(row: sqlite3.Row) -> VoiceCommandRecord:
        return VoiceCommandRecord(
            id=row["id"],
            session_id=row["session_id"],
            thread_id=row["thread_id"],
            audio_asset_id=row["audio_asset_id"],
            transcribed_text=row["transcribed_text"],
            edited_text=row["edited_text"],
            send_mode=row["send_mode"],
            detected_language=row["detected_language"],
            stt_model=row["stt_model"],
            created_at_utc=row["created_at_utc"],
            sent_message_id=row["sent_message_id"],
        )

    @staticmethod
    def _row_to_action_proposal(row: sqlite3.Row) -> ActionProposalRecord:
        return ActionProposalRecord(
            id=row["id"],
            session_id=row["session_id"],
            thread_id=row["thread_id"],
            message_id=row["message_id"],
            action_type=row["action_type"],
            title=row["title"],
            status=row["status"],
            requires_confirmation=bool(row["requires_confirmation"]),
            payload_json=row["payload_json"],
            preview_markdown=row["preview_markdown"],
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
            executed_at_utc=row["executed_at_utc"],
            error_message=row["error_message"],
        )

    @staticmethod
    def _row_to_action_execution(row: sqlite3.Row) -> ActionExecutionRecord:
        return ActionExecutionRecord(
            id=row["id"],
            action_proposal_id=row["action_proposal_id"],
            created_at_utc=row["created_at_utc"],
            executor_kind=row["executor_kind"],
            status=row["status"],
            result_json=row["result_json"],
        )

    @staticmethod
    def _row_to_export_artifact(row: sqlite3.Row) -> ExportArtifactRecord:
        return ExportArtifactRecord(
            id=row["id"],
            session_id=row["session_id"],
            action_proposal_id=row["action_proposal_id"],
            file_path=row["file_path"],
            file_name=row["file_name"],
            mime_type=row["mime_type"],
            size_bytes=int(row["size_bytes"]),
            created_at_utc=row["created_at_utc"],
            kind=row["kind"],
        )

    @staticmethod
    def _row_to_transcript_correction_proposal(
        row: sqlite3.Row,
    ) -> TranscriptCorrectionProposalRecord:
        return TranscriptCorrectionProposalRecord(
            id=row["id"],
            session_id=row["session_id"],
            base_revision_id=row["base_revision_id"],
            status=row["status"],
            scope_json=row["scope_json"],
            strategy=row["strategy"],
            model_name=row["model_name"],
            before_snapshot_json=row["before_snapshot_json"],
            after_snapshot_json=row["after_snapshot_json"],
            diff_preview_json=row["diff_preview_json"],
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
            applied_revision_id=row["applied_revision_id"],
            warnings_json=row["warnings_json"],
        )
