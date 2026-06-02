from __future__ import annotations

import difflib
import json
import os
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal

from backend.app.config import AppSettings
from backend.app.services.local_llm import resolve_local_llm_config
from backend.app.services.retrieval import TranscriptRetriever
from backend.app.store import SQLiteStore, TranscriptRevisionRecord, TranscriptSegmentRecord

CorrectionScopeType = Literal["full_transcript", "segment_ids", "time_range_ms"]
CorrectionStrategyRequest = Literal["auto", "llm", "rules"]
CorrectionStrategyUsed = Literal["llm", "rules", "llm_then_rules"]


@dataclass(frozen=True)
class SegmentCorrectionChange:
    segment_id: str
    segment_index: int
    start_ms: int
    end_ms: int
    before_text: str
    after_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "segment_index": self.segment_index,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "before_text": self.before_text,
            "after_text": self.after_text,
        }


@dataclass(frozen=True)
class TranscriptCorrectionProposalResult:
    proposal_id: str
    session_id: str
    base_revision_id: str
    strategy_used: str
    model_name: str
    changed_segment_count: int
    warnings: list[str]
    diff_preview: dict[str, Any]
    segment_changes: list[SegmentCorrectionChange]

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "session_id": self.session_id,
            "base_revision_id": self.base_revision_id,
            "strategy_used": self.strategy_used,
            "model_name": self.model_name,
            "changed_segment_count": self.changed_segment_count,
            "warnings": self.warnings,
            "diff_preview": self.diff_preview,
            "segment_changes": [item.to_dict() for item in self.segment_changes],
        }


@dataclass(frozen=True)
class TranscriptCorrectionApplyResult:
    proposal_id: str
    status: str
    applied_revision_id: str
    revision_number: int
    changed_segment_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "status": self.status,
            "applied_revision_id": self.applied_revision_id,
            "revision_number": self.revision_number,
            "changed_segment_count": self.changed_segment_count,
        }


def _normalize_text_rules(text: str) -> str:
    value = text.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([!?.,]){2,}", lambda m: m.group(0)[0], value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ""
    # Capitalize first character and sentence starts (simple heuristic).
    chars = list(value)
    chars[0] = chars[0].upper()
    for idx in range(1, len(chars) - 1):
        if chars[idx] in ".!?" and chars[idx + 1] == " " and idx + 2 < len(chars):
            chars[idx + 2] = chars[idx + 2].upper()
    value = "".join(chars)
    return value


def _build_ollama_correction_prompt(segments: list[TranscriptSegmentRecord]) -> str:
    segment_payload = [
        {
            "segment_id": segment.id,
            "segment_index": segment.segment_index,
            "text": segment.text,
        }
        for segment in segments
    ]
    return (
        "You correct transcript segments and return JSON only.\n"
        'Return exactly this shape: {"segments":[{"segment_id":"...","text":"..."}]}.\n'
        "Rules:\n"
        "- Keep exactly the same segment_ids.\n"
        "- Keep the same language as the input.\n"
        "- Do not summarize, translate, merge, split, or omit segments.\n"
        "- Only correct punctuation, capitalization, spacing, and obvious ASR mistakes.\n"
        "- Preserve speaker meaning.\n\n"
        f"Segments:\n{json.dumps(segment_payload, ensure_ascii=False)}"
    )


def _build_ollama_correction_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "segment_id": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["segment_id", "text"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["segments"],
        "additionalProperties": False,
    }


def _resolve_ollama_chat_url() -> str:
    explicit_chat_url = (os.getenv("TRANSCIBIO_OLLAMA_CHAT_URL") or "").strip()
    if explicit_chat_url:
        return explicit_chat_url

    generate_url = (os.getenv("TRANSCIBIO_OLLAMA_GENERATE_URL") or "").strip()
    if generate_url.endswith("/api/generate"):
        return f"{generate_url[: -len('/api/generate')]}/api/chat"
    if generate_url:
        return generate_url

    return "http://127.0.0.1:11434/api/chat"


def _resolve_ollama_correction_timeout_seconds() -> float:
    raw_timeout = (os.getenv("TRANSCIBIO_OLLAMA_CORRECTION_TIMEOUT_SECONDS") or "").strip()
    if not raw_timeout:
        return 180.0
    try:
        parsed = float(raw_timeout)
    except ValueError:
        return 180.0
    if parsed <= 0:
        return 180.0
    return parsed


def _post_ollama_json(
    url: str, payload: dict[str, Any], *, timeout_seconds: float
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
    except socket.timeout as exc:
        raise RuntimeError(
            f"Ollama correction request timed out after {timeout_seconds:g}s."
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Ollama correction request failed: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise RuntimeError("Ollama correction returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Ollama correction response must be a JSON object.")
    return parsed


def _strip_markdown_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _parse_json_object_text(raw_text: str) -> dict[str, Any]:
    candidates = [raw_text.strip()]

    unfenced = _strip_markdown_code_fences(raw_text)
    if unfenced not in candidates:
        candidates.append(unfenced)

    extracted = _extract_first_json_object(unfenced)
    if extracted and extracted not in candidates:
        candidates.append(extracted)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError("Ollama correction content was not valid JSON.")


def _parse_ollama_correction_response(
    response_payload: dict[str, Any],
    segments: list[TranscriptSegmentRecord],
) -> dict[str, str]:
    raw_response = ""
    message = response_payload.get("message")
    if isinstance(message, dict):
        message_content = message.get("content")
        if isinstance(message_content, str):
            raw_response = message_content
    if not raw_response:
        fallback_response = response_payload.get("response")
        if isinstance(fallback_response, str):
            raw_response = fallback_response
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise RuntimeError("Ollama correction returned empty content.")
    parsed = _parse_json_object_text(raw_response)

    items = parsed.get("segments")
    if not isinstance(items, list):
        raise RuntimeError("Ollama correction JSON must include a 'segments' list.")

    expected_ids = {segment.id for segment in segments}
    corrected: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        segment_id = item.get("segment_id")
        text = item.get("text")
        if not isinstance(segment_id, str) or segment_id not in expected_ids:
            continue
        if not isinstance(text, str):
            continue
        normalized = text.strip()
        if normalized:
            corrected[segment_id] = normalized

    missing_ids = [segment.id for segment in segments if segment.id not in corrected]
    if missing_ids:
        raise RuntimeError("Ollama correction omitted one or more transcript segments.")
    return corrected


class TranscriptCorrectionService:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        settings: AppSettings,
        retriever: TranscriptRetriever | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._retriever = retriever or TranscriptRetriever(store, settings)

    def generate_proposal(
        self,
        *,
        session_id: str,
        revision_id: str | None = None,
        scope_type: CorrectionScopeType = "full_transcript",
        segment_ids: list[str] | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
        strategy: CorrectionStrategyRequest = "auto",
    ) -> TranscriptCorrectionProposalResult:
        base_revision = self._resolve_revision(session_id=session_id, revision_id=revision_id)
        segments = self._resolve_segments_for_scope(
            revision=base_revision,
            scope_type=scope_type,
            segment_ids=segment_ids or [],
            start_ms=start_ms,
            end_ms=end_ms,
        )
        if not segments:
            raise ValueError("No transcript segments matched the requested correction scope.")

        warnings: list[str] = []
        model_name = ""
        strategy_used: CorrectionStrategyUsed = "rules"

        corrected_by_segment_id: dict[str, str] | None = None
        if strategy in {"auto", "llm"}:
            corrected_by_segment_id, llm_model_name, llm_warning = self._try_llm_correction(
                segments
            )
            if llm_warning:
                warnings.append(llm_warning)
            if corrected_by_segment_id is not None:
                model_name = llm_model_name
                strategy_used = "llm"
            elif strategy == "auto":
                strategy_used = "llm_then_rules"

        if corrected_by_segment_id is None:
            corrected_by_segment_id = {
                segment.id: _normalize_text_rules(segment.text) for segment in segments
            }
            model_name = model_name or "rules"

        changes: list[SegmentCorrectionChange] = []
        for segment in segments:
            after_text = (corrected_by_segment_id.get(segment.id) or segment.text).strip()
            if not after_text:
                after_text = segment.text
                warnings.append(
                    f"Correction produced empty text for segment {segment.segment_index}; original kept."
                )
            if after_text != segment.text:
                changes.append(
                    SegmentCorrectionChange(
                        segment_id=segment.id,
                        segment_index=segment.segment_index,
                        start_ms=segment.start_ms,
                        end_ms=segment.end_ms,
                        before_text=segment.text,
                        after_text=after_text,
                    )
                )

        if not changes:
            warnings.append("No correction changes were proposed for the selected scope.")

        diff_preview = self._build_diff_preview(changes)
        proposal_record = self._store.create_transcript_correction_proposal(
            session_id=session_id,
            base_revision_id=base_revision.id,
            status="pending",
            scope={
                "scope_type": scope_type,
                "segment_ids": [segment.id for segment in segments]
                if scope_type == "segment_ids"
                else [],
                "start_ms": start_ms,
                "end_ms": end_ms,
            },
            strategy=strategy_used,
            model_name=model_name,
            before_snapshot={
                "revision_id": base_revision.id,
                "segments": [
                    {
                        "segment_id": segment.id,
                        "segment_index": segment.segment_index,
                        "text": segment.text,
                    }
                    for segment in segments
                ],
            },
            after_snapshot={
                "revision_id": base_revision.id,
                "segments": [
                    {
                        "segment_id": segment.id,
                        "segment_index": segment.segment_index,
                        "text": next(
                            (
                                change.after_text
                                for change in changes
                                if change.segment_id == segment.id
                            ),
                            segment.text,
                        ),
                    }
                    for segment in segments
                ],
            },
            diff_preview=diff_preview,
            warnings=warnings,
        )

        return TranscriptCorrectionProposalResult(
            proposal_id=proposal_record.id,
            session_id=session_id,
            base_revision_id=base_revision.id,
            strategy_used=strategy_used,
            model_name=model_name,
            changed_segment_count=len(changes),
            warnings=warnings,
            diff_preview=diff_preview,
            segment_changes=changes,
        )

    def get_proposal(
        self, *, session_id: str, proposal_id: str
    ) -> TranscriptCorrectionProposalResult:
        proposal = self._store.get_transcript_correction_proposal(proposal_id)
        if proposal is None or proposal.session_id != session_id:
            raise KeyError("proposal_not_found")
        return self._proposal_record_to_result(proposal)

    def apply_proposal(
        self,
        *,
        session_id: str,
        proposal_id: str,
        actor: str = "user",
    ) -> TranscriptCorrectionApplyResult:
        proposal = self._store.get_transcript_correction_proposal(proposal_id)
        if proposal is None or proposal.session_id != session_id:
            raise KeyError("proposal_not_found")
        if proposal.status == "applied":
            raise ValueError("Correction proposal was already applied.")
        if proposal.status != "pending":
            raise ValueError(
                f"Correction proposal cannot be applied from status '{proposal.status}'."
            )

        latest_revision = self._store.get_latest_transcript_revision_for_session(session_id)
        if latest_revision is None:
            raise ValueError("No transcript available for this session.")
        if latest_revision.id != proposal.base_revision_id:
            self._store.update_transcript_correction_proposal(proposal.id, status="expired")
            raise RuntimeError(
                "Transcript has changed since this proposal was generated. Regenerate and try again."
            )

        after_snapshot = json.loads(proposal.after_snapshot_json)
        if not isinstance(after_snapshot, dict):
            raise RuntimeError("Correction proposal payload is invalid (after snapshot).")
        segment_items = after_snapshot.get("segments") or []
        overrides: dict[str, str] = {}
        for item in segment_items:
            if not isinstance(item, dict):
                continue
            segment_id = item.get("segment_id")
            text = item.get("text")
            if isinstance(segment_id, str) and segment_id and isinstance(text, str):
                segment = self._store.get_transcript_segment(segment_id)
                if segment is not None and segment.text != text:
                    overrides[segment_id] = text

        created = self._store.create_transcript_revision_from_text_overrides(
            session_id=session_id,
            base_revision_id=proposal.base_revision_id,
            segment_text_overrides=overrides or {},
            actor=actor,
            source="ai_correction_apply",
            operation_type="ai_correction_apply",
            operation_payload={
                "proposal_id": proposal.id,
                "strategy": proposal.strategy,
                "model_name": proposal.model_name,
                "changed_segment_ids": list(overrides.keys()),
            },
        )
        self._store.update_transcript_correction_proposal(
            proposal.id,
            status="applied",
            applied_revision_id=created.revision.id,
        )
        # Refresh retrieval index for the new active revision.
        self._retriever.index_revision(created.revision)
        return TranscriptCorrectionApplyResult(
            proposal_id=proposal.id,
            status="applied",
            applied_revision_id=created.revision.id,
            revision_number=created.revision.revision_number,
            changed_segment_count=len(overrides),
        )

    def _resolve_revision(
        self, *, session_id: str, revision_id: str | None
    ) -> TranscriptRevisionRecord:
        if revision_id:
            revision = self._store.get_transcript_revision(revision_id)
            if revision is None or revision.session_id != session_id:
                raise KeyError("revision_not_found")
            return revision
        revision = self._store.get_latest_transcript_revision_for_session(session_id)
        if revision is None:
            raise ValueError("No transcript found for this session.")
        return revision

    def _resolve_segments_for_scope(
        self,
        *,
        revision: TranscriptRevisionRecord,
        scope_type: CorrectionScopeType,
        segment_ids: list[str],
        start_ms: int | None,
        end_ms: int | None,
    ):
        segments = self._store.list_transcript_segments(revision.id)
        if scope_type == "full_transcript":
            return segments
        if scope_type == "segment_ids":
            id_set = {item for item in segment_ids if item}
            return [segment for segment in segments if segment.id in id_set]
        if scope_type == "time_range_ms":
            if start_ms is None or end_ms is None:
                raise ValueError("time_range_ms scope requires start_ms and end_ms.")
            if end_ms < start_ms:
                raise ValueError("end_ms must be greater than or equal to start_ms.")
            return [
                segment
                for segment in segments
                if not (segment.end_ms < start_ms or segment.start_ms > end_ms)
            ]
        raise ValueError(f"Unsupported scope_type: {scope_type}")

    def _try_llm_correction(
        self,
        segments: list[TranscriptSegmentRecord],
    ) -> tuple[dict[str, str] | None, str, str | None]:
        llm_config = resolve_local_llm_config(store=self._store, settings=self._settings)
        if llm_config.provider != "ollama":
            return (
                None,
                "",
                "No local LLM provider configured for correction; using rules fallback.",
            )
        try:
            corrected = self._run_ollama_correction(segments, model_name=llm_config.model_name)
        except Exception as exc:
            return (
                None,
                llm_config.model_name,
                f"Ollama correction failed: {exc}; using rules fallback.",
            )
        return corrected, llm_config.model_name, None

    def _run_ollama_correction(
        self,
        segments: list[TranscriptSegmentRecord],
        *,
        model_name: str,
    ) -> dict[str, str]:
        payload = {
            "model": model_name,
            "stream": False,
            "format": _build_ollama_correction_schema(),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You correct transcript segments. Return only valid JSON matching the provided schema. "
                        "Do not add markdown, commentary, or extra keys."
                    ),
                },
                {
                    "role": "user",
                    "content": _build_ollama_correction_prompt(segments),
                },
            ],
            "options": {"temperature": 0},
        }
        url = _resolve_ollama_chat_url()
        timeout_seconds = _resolve_ollama_correction_timeout_seconds()
        response_payload = _post_ollama_json(url, payload, timeout_seconds=timeout_seconds)
        return _parse_ollama_correction_response(response_payload, segments)

    @staticmethod
    def _build_diff_preview(changes: list[SegmentCorrectionChange]) -> dict[str, Any]:
        preview_items: list[dict[str, Any]] = []
        unified_lines: list[str] = []
        for change in changes:
            diff_lines = list(
                difflib.unified_diff(
                    [change.before_text + "\n"],
                    [change.after_text + "\n"],
                    fromfile=f"segment_{change.segment_index}_before",
                    tofile=f"segment_{change.segment_index}_after",
                    lineterm="",
                )
            )
            unified_lines.extend(diff_lines)
            preview_items.append(
                {
                    "segment_id": change.segment_id,
                    "segment_index": change.segment_index,
                    "before_text": change.before_text,
                    "after_text": change.after_text,
                    "diff_lines": diff_lines,
                }
            )
        return {
            "changed_segment_count": len(changes),
            "segments": preview_items,
            "unified_diff_lines": unified_lines,
        }

    def _proposal_record_to_result(
        self,
        proposal,
    ) -> TranscriptCorrectionProposalResult:
        try:
            warnings = json.loads(proposal.warnings_json)
        except Exception:
            warnings = []
        if not isinstance(warnings, list):
            warnings = []
        try:
            diff_preview = json.loads(proposal.diff_preview_json)
        except Exception:
            diff_preview = {"changed_segment_count": 0, "segments": [], "unified_diff_lines": []}
        if not isinstance(diff_preview, dict):
            diff_preview = {"changed_segment_count": 0, "segments": [], "unified_diff_lines": []}
        try:
            before_snapshot = json.loads(proposal.before_snapshot_json)
            after_snapshot = json.loads(proposal.after_snapshot_json)
        except Exception:
            before_snapshot = {}
            after_snapshot = {}
        before_segments = {}
        if isinstance(before_snapshot, dict):
            for item in before_snapshot.get("segments", []) or []:
                if isinstance(item, dict) and isinstance(item.get("segment_id"), str):
                    before_segments[item["segment_id"]] = str(item.get("text") or "")
        segment_changes: list[SegmentCorrectionChange] = []
        if isinstance(after_snapshot, dict):
            for item in after_snapshot.get("segments", []) or []:
                if not isinstance(item, dict):
                    continue
                segment_id = item.get("segment_id")
                after_text = item.get("text")
                if not isinstance(segment_id, str) or not isinstance(after_text, str):
                    continue
                before_text = before_segments.get(segment_id, "")
                if before_text == after_text:
                    continue
                segment = self._store.get_transcript_segment(segment_id)
                if segment is None:
                    continue
                segment_changes.append(
                    SegmentCorrectionChange(
                        segment_id=segment.id,
                        segment_index=segment.segment_index,
                        start_ms=segment.start_ms,
                        end_ms=segment.end_ms,
                        before_text=before_text,
                        after_text=after_text,
                    )
                )
        return TranscriptCorrectionProposalResult(
            proposal_id=proposal.id,
            session_id=proposal.session_id,
            base_revision_id=proposal.base_revision_id,
            strategy_used=proposal.strategy,
            model_name=proposal.model_name,
            changed_segment_count=len(segment_changes),
            warnings=[str(item) for item in warnings],
            diff_preview=diff_preview,
            segment_changes=segment_changes,
        )
