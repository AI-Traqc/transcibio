from __future__ import annotations

import json
import os
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from backend.app.config import AppSettings
from backend.app.store import (
    ActionExecutionRecord,
    ActionProposalRecord,
    ExportArtifactRecord,
    SQLiteStore,
)


@dataclass(frozen=True)
class ActionConfirmResult:
    action: ActionProposalRecord
    execution: ActionExecutionRecord
    artifacts: list[ExportArtifactRecord]


@dataclass(frozen=True)
class ActionCancelResult:
    action: ActionProposalRecord
    execution: ActionExecutionRecord


class ActionOrchestrator:
    def __init__(self, *, store: SQLiteStore, settings: AppSettings) -> None:
        self._store = store
        self._settings = settings

    def confirm_action(self, *, session_id: str, action_id: str) -> ActionConfirmResult:
        action = self._store.get_action_proposal(action_id)
        if action is None or action.session_id != session_id:
            raise KeyError("action_not_found")
        if action.status == "canceled":
            raise ValueError("Canceled actions cannot be confirmed.")
        if action.status == "executed":
            artifacts = self._store.list_export_artifacts_for_action(action.id)
            executions = self._store.list_action_executions(action.id)
            if not executions:
                raise RuntimeError("Action marked executed but no execution record found.")
            return ActionConfirmResult(action=action, execution=executions[-1], artifacts=artifacts)
        if action.status != "pending":
            raise ValueError(f"Action cannot be confirmed from status '{action.status}'.")

        try:
            artifacts = self._execute_export(action)
            updated = self._store.update_action_proposal(
                action.id, status="executed", executed=True, error_message=""
            )
            execution = self._store.create_action_execution(
                action_proposal_id=action.id,
                executor_kind="local_export",
                status="succeeded",
                result={
                    "artifact_ids": [item.id for item in artifacts],
                    "artifact_count": len(artifacts),
                },
            )
            return ActionConfirmResult(action=updated, execution=execution, artifacts=artifacts)
        except Exception as exc:
            updated = self._store.update_action_proposal(
                action.id, status="error", error_message=str(exc)
            )
            execution = self._store.create_action_execution(
                action_proposal_id=action.id,
                executor_kind="local_export",
                status="failed",
                result={"error": str(exc)},
            )
            raise RuntimeError(f"Action execution failed: {exc}") from exc

    def cancel_action(self, *, session_id: str, action_id: str) -> ActionCancelResult:
        action = self._store.get_action_proposal(action_id)
        if action is None or action.session_id != session_id:
            raise KeyError("action_not_found")
        if action.status == "executed":
            raise ValueError("Executed actions cannot be canceled.")
        if action.status == "canceled":
            executions = self._store.list_action_executions(action.id)
            if not executions:
                execution = self._store.create_action_execution(
                    action_proposal_id=action.id,
                    executor_kind="cancel",
                    status="canceled",
                    result={"note": "Canceled"},
                )
            else:
                execution = executions[-1]
            return ActionCancelResult(action=action, execution=execution)

        updated = self._store.update_action_proposal(
            action.id, status="canceled", executed=False, error_message=""
        )
        execution = self._store.create_action_execution(
            action_proposal_id=action.id,
            executor_kind="cancel",
            status="canceled",
            result={"note": "Canceled by user"},
        )
        return ActionCancelResult(action=updated, execution=execution)

    def _execute_export(self, action: ActionProposalRecord) -> list[ExportArtifactRecord]:
        try:
            payload = json.loads(action.payload_json)
        except Exception as exc:
            raise ValueError("Action payload JSON is invalid.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Action payload must be an object.")

        export_dir = self._settings.sessions_root / action.session_id / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        if action.action_type == "email_draft":
            return self._export_email_draft(action, payload, export_dir)
        if action.action_type == "task_draft":
            return self._export_task_draft(action, payload, export_dir)
        if action.action_type in {"note_export", "doc_export"}:
            return self._export_note_or_doc(action, payload, export_dir)
        raise ValueError(f"Unsupported action type: {action.action_type}")

    def _export_email_draft(
        self,
        action: ActionProposalRecord,
        payload: dict[str, Any],
        export_dir: Path,
    ) -> list[ExportArtifactRecord]:
        subject = str(payload.get("subject") or "Follow-up")
        recipient = str(payload.get("to") or "")
        body_markdown = str(payload.get("body_markdown") or action.preview_markdown or "")
        body_text = str(payload.get("body_text") or body_markdown)

        md_name = f"email_{action.id}.md"
        md_path = export_dir / md_name
        md_path.write_text(
            f"# Email Draft\n\nTo: {recipient or '[recipient]'}\n\nSubject: {subject}\n\n{body_markdown}\n",
            encoding="utf-8",
        )

        json_name = f"email_{action.id}.json"
        json_path = export_dir / json_name
        json_path.write_text(
            json.dumps(
                {
                    "action_id": action.id,
                    "type": "email_draft",
                    "to": recipient,
                    "subject": subject,
                    "body_text": body_text,
                    "body_markdown": body_markdown,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        eml_name = f"email_{action.id}.eml"
        eml_path = export_dir / eml_name
        message = EmailMessage()
        if recipient:
            message["To"] = recipient
        message["Subject"] = subject
        message["From"] = "transcibio-local@localhost"
        message.set_content(body_text)
        eml_path.write_bytes(message.as_bytes())

        return [
            self._persist_artifact(action, md_path, "text/markdown", "email_draft_md"),
            self._persist_artifact(action, json_path, "application/json", "email_draft_json"),
            self._persist_artifact(action, eml_path, "message/rfc822", "email_draft_eml"),
        ]

    def _export_task_draft(
        self,
        action: ActionProposalRecord,
        payload: dict[str, Any],
        export_dir: Path,
    ) -> list[ExportArtifactRecord]:
        tasks = payload.get("tasks")
        if not isinstance(tasks, list):
            tasks = [payload.get("title") or action.title]
        normalized_tasks = [str(item).strip() for item in tasks if str(item).strip()]
        md_name = f"tasks_{action.id}.md"
        md_path = export_dir / md_name
        md_path.write_text(
            "# Task Draft\n\n" + "\n".join(f"- [ ] {item}" for item in normalized_tasks) + "\n",
            encoding="utf-8",
        )
        json_name = f"tasks_{action.id}.json"
        json_path = export_dir / json_name
        json_path.write_text(
            json.dumps(
                {"action_id": action.id, "type": "task_draft", "tasks": normalized_tasks},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return [
            self._persist_artifact(action, md_path, "text/markdown", "task_draft_md"),
            self._persist_artifact(action, json_path, "application/json", "task_draft_json"),
        ]

    def _export_note_or_doc(
        self,
        action: ActionProposalRecord,
        payload: dict[str, Any],
        export_dir: Path,
    ) -> list[ExportArtifactRecord]:
        title = str(payload.get("title") or action.title)
        body_markdown = str(payload.get("body_markdown") or action.preview_markdown or "")
        stem = "note" if action.action_type == "note_export" else "doc"
        md_name = f"{stem}_{action.id}.md"
        md_path = export_dir / md_name
        md_path.write_text(f"# {title}\n\n{body_markdown}\n", encoding="utf-8")
        json_name = f"{stem}_{action.id}.json"
        json_path = export_dir / json_name
        json_path.write_text(
            json.dumps(
                {
                    "action_id": action.id,
                    "type": action.action_type,
                    "title": title,
                    "body_markdown": body_markdown,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return [
            self._persist_artifact(action, md_path, "text/markdown", f"{action.action_type}_md"),
            self._persist_artifact(
                action, json_path, "application/json", f"{action.action_type}_json"
            ),
        ]

    def _persist_artifact(
        self,
        action: ActionProposalRecord,
        path: Path,
        mime_type: str,
        kind: str,
    ) -> ExportArtifactRecord:
        rel = os.path.relpath(path, self._settings.data_root).replace("\\", "/")
        return self._store.create_export_artifact(
            session_id=action.session_id,
            action_proposal_id=action.id,
            file_path=rel,
            file_name=path.name,
            mime_type=mime_type,
            size_bytes=path.stat().st_size,
            kind=kind,
        )
