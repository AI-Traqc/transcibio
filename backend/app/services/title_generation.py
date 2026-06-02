from __future__ import annotations

import json
import os
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from backend.app.store import SQLiteStore

_DEFAULT_TITLE = "New session"


def generate_session_title(
    transcript_text: str,
    *,
    store: SQLiteStore,
    session_id: str,
    model_name: str = "",
) -> None:
    session = store.get_session(session_id)
    if session is None:
        return
    if session.title != _DEFAULT_TITLE:
        return

    text = transcript_text.strip()
    if not text:
        return

    excerpt = " ".join(text.split()[:500])
    title = _generate_via_ollama(excerpt, model_name=model_name)
    if not title:
        title = _fallback_title(text)
    if not title:
        return

    store.update_session_title(session_id, title)


def _generate_via_ollama(excerpt: str, *, model_name: str) -> str:
    model = model_name or os.getenv("TRANSCIBIO_OLLAMA_MODEL", "gpt-oss-20b")
    url = os.getenv("TRANSCIBIO_OLLAMA_GENERATE_URL", "http://127.0.0.1:11434/api/generate")

    prompt = (
        "Generate a short descriptive title (max 8 words) for the following meeting transcript. "
        "Output only the title, nothing else. Match the language of the transcript.\n\n"
        f"Transcript:\n{excerpt}"
    )

    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 30},
        }
    ).encode()

    try:
        req = Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=15) as resp:  # noqa: S310
            data = json.loads(resp.read())
        raw = data.get("response", "").strip()
        return _sanitize_title(raw)
    except (URLError, OSError, json.JSONDecodeError, KeyError):
        return ""


def _fallback_title(text: str) -> str:
    words = text.split()[:6]
    if not words:
        return ""
    title = " ".join(words)
    if len(text.split()) > 6:
        title += "..."
    return title[:60]


def _sanitize_title(raw: str) -> str:
    cleaned = raw.strip().strip('"').strip("'").strip("*").strip("#")
    cleaned = re.sub(r"^(Title|Titel|Thema)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    if not cleaned or len(cleaned) < 2:
        return ""
    return cleaned[:80]
