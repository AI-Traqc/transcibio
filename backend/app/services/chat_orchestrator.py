from __future__ import annotations

import json
import os
import queue
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Protocol

from backend.app.config import AppSettings
from backend.app.services.local_llm import resolve_local_llm_config
from backend.app.services.retrieval import RetrievalHit, TranscriptRetriever
from backend.app.services.text_chunking import SentenceChunker
from backend.app.services.tts_streaming import StreamingTtsEngine
from backend.app.store import (
    MessageCitationInput,
    SQLiteStore,
    TranscriptRevisionRecord,
)


def _format_timestamp_ms(ms: int) -> str:
    total_seconds = max(0, int(ms // 1000))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


_SEGMENT_MARKER_RE = re.compile(r"\[SEG:([a-fA-F0-9]+)\]")


@dataclass(frozen=True)
class ChatModelRequest:
    user_message: str
    transcript_context: str
    response_language: str
    for_speech: bool = False  # voice mode: reply as plain spoken prose, not markdown


@dataclass(frozen=True)
class ChatModelResponse:
    content_markdown: str
    model_name: str


class ChatModelClient(Protocol):
    def generate(self, request: ChatModelRequest) -> ChatModelResponse:
        """Generate a markdown response using the provided grounded context."""


class StreamingChatModelClient(Protocol):
    def generate_stream(self, request: ChatModelRequest) -> Iterator[str]:
        """Yield response text deltas as the model produces them."""


class RuleBasedChatModelClient:
    """Deterministic local fallback to keep the transcript chat path working offline."""

    def generate(self, request: ChatModelRequest) -> ChatModelResponse:
        de = request.response_language == "de"
        bullet_lines = [
            line.strip()
            for line in request.transcript_context.splitlines()
            if line.strip().startswith("- ")
        ]
        if not bullet_lines:
            content = (
                "Ich konnte keine passenden Transkriptstellen für diese Anfrage finden. "
                "Bitte formuliere die Frage genauer oder bearbeite zuerst das Transkript."
                if de
                else "I could not find relevant transcript passages for this request. "
                "Try using more specific wording or editing the transcript first."
            )
            return ChatModelResponse(content_markdown=content, model_name="rule-based-fallback")

        selected = [line[2:] for line in bullet_lines[:4]]
        lead = (
            "Ich habe folgende relevante Punkte aus dem Transkript gefunden:"
            if de
            else "I found the following relevant points from the transcript:"
        )
        if request.for_speech:
            # Voice fallback: plain spoken prose in the locked language, no markdown.
            spoken = " ".join(s if s.endswith((".", "!", "?")) else f"{s}." for s in selected)
            return ChatModelResponse(
                content_markdown=f"{lead} {spoken}".strip(),
                model_name="rule-based-fallback",
            )

        heading = "## Transkriptbasierte Antwort" if de else "## Transcript-grounded response"
        offer = (
            "Auf Wunsch kann ich daraus auch eine Folge-E-Mail, eine Aufgabenliste oder "
            "eine Notiz erstellen."
            if de
            else "If you want, I can also draft a follow-up email, task list, or note "
            "export based on these points."
        )
        answer_lines = [heading, "", lead, ""]
        answer_lines.extend(f"- {s}" for s in selected)
        answer_lines.extend(["", offer])
        return ChatModelResponse(
            content_markdown="\n".join(answer_lines).strip(),
            model_name="rule-based-fallback",
        )

    def generate_stream(self, request: ChatModelRequest) -> Iterator[str]:
        # No real streaming offline; emit the full deterministic answer at once.
        yield self.generate(request).content_markdown


class LocalChatHttpError(RuntimeError):
    """A non-2xx HTTP response from a local chat backend, carrying status + body.

    Distinct from the generic ``RuntimeError`` used for transport failures so callers
    can inspect the response (e.g. retry a request that an older model rejected).
    """

    def __init__(self, provider: str, status: int, body: str) -> None:
        super().__init__(f"{provider} request failed: HTTP {status} {body[:200]}".strip())
        self.status = status
        self.body = body


def _read_http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", "replace")
    except Exception:
        return ""


class _HttpLocalChatClient:
    def __init__(self, *, url: str, provider_name: str) -> None:
        self._url = url
        self._provider_name = provider_name

    def _post_json(self, payload: dict, *, timeout: float = 120.0) -> dict:
        req = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise LocalChatHttpError(
                self._provider_name, exc.code, _read_http_error_body(exc)
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"{self._provider_name} request failed: {exc}") from exc
        try:
            return json.loads(body)
        except Exception as exc:
            raise RuntimeError(f"{self._provider_name} returned invalid JSON") from exc

    def _iter_lines(self, payload: dict, *, timeout: float = 180.0) -> Iterator[str]:
        req = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = urllib.request.urlopen(req, timeout=timeout)  # noqa: S310
        except urllib.error.HTTPError as exc:
            raise LocalChatHttpError(
                self._provider_name, exc.code, _read_http_error_body(exc)
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"{self._provider_name} request failed: {exc}") from exc
        with response:
            for raw in response:
                line = raw.decode("utf-8").strip()
                if line:
                    yield line


class LmStudioChatModelClient(_HttpLocalChatClient):
    def __init__(self, url: str = "http://127.0.0.1:1234/v1/chat/completions") -> None:
        super().__init__(url=url, provider_name="LM Studio")

    @staticmethod
    def _build_payload(request: ChatModelRequest) -> dict:
        return {
            "model": "local-model",
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": _system_instruction(request)},
                {"role": "user", "content": _build_user_content(request)},
            ],
        }

    def generate(self, request: ChatModelRequest) -> ChatModelResponse:
        payload = self._build_payload(request)
        data = self._post_json(payload)
        content = (((data.get("choices") or [{}])[0]).get("message") or {}).get(
            "content"
        ) or "I could not generate a response."
        return ChatModelResponse(content_markdown=str(content).strip(), model_name="lmstudio")

    def generate_stream(self, request: ChatModelRequest) -> Iterator[str]:
        payload = self._build_payload(request)
        payload["stream"] = True
        for line in self._iter_lines(payload):
            if not line.startswith("data:"):
                continue
            data_str = line[len("data:") :].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            delta = (((data.get("choices") or [{}])[0]).get("delta") or {}).get("content")
            if delta:
                yield delta


class OllamaChatModelClient(_HttpLocalChatClient):
    def __init__(
        self,
        *,
        model_name: str,
        url: str | None = None,
    ) -> None:
        # Default to the configured endpoint so non-localhost deployments (Docker,
        # remote host) work; falls back to localhost for native single-machine use.
        super().__init__(
            url=url
            or os.getenv("TRANSCIBIO_OLLAMA_GENERATE_URL", "http://127.0.0.1:11434/api/generate"),
            provider_name="Ollama",
        )
        self._model_name = model_name

    # Reasoning models (qwen3, gpt-oss, ...) stream chain-of-thought into a separate
    # `thinking` field whose tokens count against num_predict; for a long prompt the
    # reasoning can exhaust the whole budget before a single answer token is emitted,
    # yielding an empty (silent) voice turn. Voice wants short, low-latency spoken
    # replies, so we disable reasoning for voice turns. `False` fully disables it on
    # hybrid models such as qwen3 (verified: instant answer, no reasoning). Models that
    # reject the `think` field (HTTP 400) fall back to a no-think retry below.
    _VOICE_THINK: bool | str = False

    def _build_payload(
        self, request: ChatModelRequest, *, stream: bool, think: bool | str | None = None
    ) -> dict:
        payload = {
            "model": self._model_name,
            "stream": stream,
            "prompt": _build_prompt_text(request),
            "options": {
                "temperature": 0.2,
                "num_predict": 1024,
                "num_ctx": 8192,
            },
        }
        if think is not None:
            payload["think"] = think
        return payload

    @staticmethod
    def _should_retry_without_think(think: bool | str | None, exc: LocalChatHttpError) -> bool:
        return think is not None and exc.status == 400 and "think" in exc.body.lower()

    def generate(self, request: ChatModelRequest) -> ChatModelResponse:
        think = self._VOICE_THINK if request.for_speech else None
        try:
            data = self._post_json(
                self._build_payload(request, stream=False, think=think), timeout=180.0
            )
        except LocalChatHttpError as exc:
            if not self._should_retry_without_think(think, exc):
                raise
            data = self._post_json(self._build_payload(request, stream=False), timeout=180.0)
        content = data.get("response") or "I could not generate a response."
        return ChatModelResponse(content_markdown=str(content).strip(), model_name="ollama")

    def _iter_response_chunks(
        self, request: ChatModelRequest, think: bool | str | None
    ) -> Iterator[str]:
        for line in self._iter_lines(self._build_payload(request, stream=True, think=think)):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            chunk = data.get("response")
            if chunk:
                yield chunk
            if data.get("done"):
                break

    def generate_stream(self, request: ChatModelRequest) -> Iterator[str]:
        think = self._VOICE_THINK if request.for_speech else None
        emitted = False
        try:
            for chunk in self._iter_response_chunks(request, think):
                emitted = True
                yield chunk
            return
        except LocalChatHttpError as exc:
            # The thinking-unsupported error is raised before streaming begins, so a
            # retry is only safe (no duplicated output) when nothing was emitted yet.
            if emitted or not self._should_retry_without_think(think, exc):
                raise
        yield from self._iter_response_chunks(request, None)


def _language_instruction(language: str) -> str:
    return "Antworte auf Deutsch." if language == "de" else f"Respond in {language}."


def _speech_language_lock(language: str) -> str:
    """Hard language lock for voice mode: the TTS engine can only speak one language,
    so the reply must stay in it regardless of the language the user spoke in."""
    if language == "de":
        return (
            "Antworte ausschließlich auf Deutsch. Auch wenn der Nutzer eine andere "
            "Sprache spricht oder die Frage auf Englisch erscheint, antworte immer "
            "vollständig auf Deutsch."
        )
    return (
        f"Respond only in {language}. Even if the user speaks another language, "
        f"always answer in {language}."
    )


def _speech_system_instruction(request: ChatModelRequest) -> str:
    """Voice-mode prompt: the reply is read aloud, so produce plain spoken prose.

    When the locked language is German the *entire* instruction is written in German
    and the language directive is repeated at the end. Small local models follow the
    dominant language of the prompt and obey the last instruction most strongly, so an
    English prompt with a single German sentence does not reliably yield German output.
    """
    lock = _speech_language_lock(request.response_language)
    if request.response_language == "de":
        parts = [
            lock,
            "Du bist ein hilfreicher Sprachassistent; deine Antwort wird von einer "
            "Sprachausgabe vorgelesen. Antworte in einfacher, natürlicher gesprochener "
            "Sprache mit kurzen, vollständigen Sätzen. Verwende kein Markdown, keine "
            "Überschriften, keine Aufzählungspunkte, keine nummerierten Listen, keine "
            "Tabellen, keine Codeblöcke und keine Emojis. Wenn du etwas aufzählen musst, "
            "formuliere es als fließenden Text (zum Beispiel: zuerst..., dann..., "
            "schließlich...). Halte die Antwort kurz und gut hörbar.",
        ]
        if request.transcript_context.strip():
            parts.append(
                "Ein Besprechungstranskript ist als Kontext angegeben. Wenn sich die Frage "
                "darauf bezieht, antworte aus diesem Kontext und markiere zitierte Fakten "
                "mit [SEG:<segment_id>]-Markern (diese werden vor dem Vorlesen entfernt). "
                "Wenn das Transkript die Frage nicht abdeckt, antworte aus deinem "
                "Allgemeinwissen."
            )
        # Repeat the lock last: the final instruction has the strongest effect.
        parts.append(lock)
        return " ".join(parts)

    parts = [
        lock,
        "You are a helpful voice assistant; your reply will be read aloud by a "
        "text-to-speech engine. Reply in plain, natural spoken language using short, "
        "complete sentences. Do not use markdown, headings, bullet points, numbered "
        "lists, tables, code blocks, or emojis. If you need to enumerate things, say "
        "them as flowing prose (for example: first..., then..., finally...). Keep the "
        "answer brief and easy to follow by ear.",
    ]
    if request.transcript_context.strip():
        parts.append(
            "A meeting transcript is provided as context. When the question relates to it, "
            "answer from that context and mark cited facts with [SEG:<segment_id>] markers "
            "(these are removed before speaking). If the transcript does not cover the "
            "question, answer from your general knowledge."
        )
    return " ".join(parts)


def _system_instruction(request: ChatModelRequest) -> str:
    """Blend prompt: ground in the transcript when present, else general assistant.

    Two output modes: markdown for typed chat, plain spoken prose for voice mode.
    """
    if request.for_speech:
        return _speech_system_instruction(request)
    parts = [
        _language_instruction(request.response_language),
        "You are a helpful, concise assistant.",
    ]
    if request.transcript_context.strip():
        parts.append(
            "A meeting transcript is provided as context. When the user's question relates to it, "
            "answer from that context and cite facts with [SEG:<segment_id>] markers. If the "
            "transcript does not cover the question, answer from your general knowledge."
        )
    parts.append("Answer in markdown.")
    return " ".join(parts)


def _build_user_content(request: ChatModelRequest) -> str:
    # Label the user turn in German for German voice turns so the section closest to
    # generation is German too (a possibly English-transcribed user message otherwise
    # pulls a small model toward English).
    de = request.for_speech and request.response_language == "de"
    transcript_label = "Transkript-Kontext" if de else "Transcript context"
    request_label = "Anfrage des Nutzers" if de else "User request"
    sections = []
    if request.transcript_context.strip():
        sections.append(f"{transcript_label}:\n{request.transcript_context}")
    sections.append(f"{request_label}:\n{request.user_message}")
    return "\n\n".join(sections)


def _build_prompt_text(request: ChatModelRequest) -> str:
    # Single-prompt form for backends without a system role (Ollama /api/generate).
    # The concatenated form loses role separation, so for German voice turns we end
    # with an explicit German answer cue to bias the first generated token toward
    # German. Ollama only echoes the generated `response`, so the cue is not spoken.
    base = f"{_system_instruction(request)}\n\n{_build_user_content(request)}"
    if request.for_speech and request.response_language == "de":
        return f"{base}\n\nAntwort (auf Deutsch):"
    return base


_FULL_TRANSCRIPT_KEYWORDS = (
    # English
    "summar",
    "overview",
    "key point",
    "key points",
    "key decision",
    "key decisions",
    "main point",
    "main points",
    "main topic",
    "main idea",
    "tl;dr",
    "identify speakers",
    "list all",
    "translate",
    "entire transcript",
    "whole transcript",
    "full transcript",
    "action item",
    "action items",
    "minutes",
    "recap",
    # German
    "zusammenfass",
    "zusammenfassung",
    "fasse",
    "ueberblick",
    "\u00fcberblick",
    "kernaussage",
    "hauptpunkt",
    "hauptpunkte",
    "kernentscheid",
    "entscheidung",
    "wichtigste",
    "protokoll",
    "\u00fcbersetze",
    "uebersetze",
    "sprecher identif",
    "sprecher erkennen",
)


def _needs_full_transcript(user_message: str) -> bool:
    lowered = user_message.lower()
    return any(keyword in lowered for keyword in _FULL_TRANSCRIPT_KEYWORDS)


@dataclass(frozen=True)
class ChatReplyJobInput:
    session_id: str
    thread_id: str
    user_message_id: str
    assistant_message_id: str
    transcript_revision_id: str | None = None


@dataclass(frozen=True)
class ChatReplyJobResult:
    assistant_message_id: str
    transcript_revision_id: str
    retrieval_hit_count: int
    citation_count: int
    model_name: str

    def to_dict(self) -> dict[str, object]:
        return {
            "assistant_message_id": self.assistant_message_id,
            "transcript_revision_id": self.transcript_revision_id,
            "retrieval_hit_count": self.retrieval_hit_count,
            "citation_count": self.citation_count,
            "model_name": self.model_name,
        }


@dataclass(frozen=True)
class VoiceTurnEvent:
    """One event in a streaming voice turn: a spoken sentence or the terminal marker."""

    kind: str  # "sentence" | "done"
    text: str = ""
    pcm: bytes = b""  # raw int16 mono PCM for this sentence ("sentence" only)
    assistant_message_id: str = ""
    model_name: str = ""


class CitationValidationError(RuntimeError):
    pass


class ChatOrchestrator:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        settings: AppSettings,
        retriever: TranscriptRetriever,
        model_client: ChatModelClient | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._retriever = retriever
        self._model_client = model_client

    def run_chat_reply_job(
        self,
        payload: ChatReplyJobInput,
        *,
        on_event: Callable[[str, dict[str, object]], None] | None = None,
    ) -> ChatReplyJobResult:
        def emit(event_type: str, event_payload: dict[str, object]) -> None:
            if on_event is not None:
                on_event(event_type, event_payload)

        user_message = self._store.get_chat_message(payload.user_message_id)
        assistant_message = self._store.get_chat_message(payload.assistant_message_id)
        if user_message is None or assistant_message is None:
            raise RuntimeError("Chat messages not found for reply job.")
        # Defensive session scoping: reject stale / cross-session job payloads so a
        # recycled job_id or thread_id cannot cause us to answer with another
        # session's context.
        if (
            user_message.session_id != payload.session_id
            or assistant_message.session_id != payload.session_id
            or user_message.thread_id != payload.thread_id
            or assistant_message.thread_id != payload.thread_id
        ):
            raise RuntimeError("Chat messages do not belong to the job's session/thread.")

        revision = self._resolve_revision(
            session_id=payload.session_id,
            requested_revision_id=payload.transcript_revision_id
            or user_message.transcript_revision_id,
        )

        emit("chat.retrieval.started", {"progress": 0.15})
        index_info, hits, needs_full, model_request = self._retrieve_and_build_request(
            revision=revision, user_text=user_message.content_plain_text
        )
        emit(
            "chat.retrieval.completed",
            {
                "progress": 0.35,
                "hit_count": len(hits),
                "chunk_count": index_info.chunk_count if index_info else 0,
                "index_meta_path": index_info.meta_path if index_info else "",
                "full_transcript": needs_full,
            },
        )
        emit("chat.llm.started", {"progress": 0.45})
        model_client = self._resolve_model_client()
        try:
            model_response = model_client.generate(model_request)
        except Exception:
            # Always fall back to deterministic local path so the chat milestone works offline.
            model_response = RuleBasedChatModelClient().generate(model_request)
        emit("chat.llm.completed", {"progress": 0.7, "model_name": model_response.model_name})

        final_markdown, citations = self._validate_and_render_citations(
            raw_markdown=model_response.content_markdown,
            revision=revision,
            hits=hits,
        )
        self._store.update_chat_message(
            payload.assistant_message_id,
            content_markdown=final_markdown,
            content_plain_text=_strip_markdown(final_markdown),
            status="completed",
            model_name=model_response.model_name,
            metadata={
                "retrieval_hit_count": len(hits),
                "indexed_chunk_count": index_info.chunk_count if index_info else 0,
                "index_meta_path": index_info.meta_path if index_info else "",
                "index_vectors_path": index_info.vectors_path if index_info else "",
            },
        )
        if citations:
            self._store.create_message_citations(
                message_id=payload.assistant_message_id, citations=citations
            )
        emit("chat.citations.ready", {"progress": 0.9, "citation_count": len(citations)})
        action_ids = self._extract_and_persist_action_proposals(
            session_id=payload.session_id,
            thread_id=payload.thread_id,
            user_message=user_message.content_plain_text,
            assistant_message_id=payload.assistant_message_id,
            assistant_markdown=final_markdown,
        )
        if action_ids:
            emit("chat.action_proposals.ready", {"progress": 0.95, "action_count": len(action_ids)})
        emit(
            "chat.assistant.completed",
            {"progress": 1.0, "assistant_message_id": payload.assistant_message_id},
        )

        return ChatReplyJobResult(
            assistant_message_id=payload.assistant_message_id,
            transcript_revision_id=revision.id if revision else "",
            retrieval_hit_count=len(hits),
            citation_count=len(citations),
            model_name=model_response.model_name,
        )

    def stream_voice_turn(
        self,
        *,
        session_id: str,
        thread_id: str,
        user_message_id: str,
        assistant_message_id: str,
        engine: StreamingTtsEngine,
        transcript_revision_id: str | None = None,
    ) -> Iterator[VoiceTurnEvent]:
        """Stream a spoken answer: LLM tokens -> sentence chunks -> TTS PCM.

        Yields one ``VoiceTurnEvent`` per spoken sentence (text + PCM), then a
        terminal ``done`` event after persisting the assistant message (with the
        same citation handling as the typed-chat path).
        """
        user_message = self._store.get_chat_message(user_message_id)
        assistant_message = self._store.get_chat_message(assistant_message_id)
        if user_message is None or assistant_message is None:
            raise RuntimeError("Chat messages not found for voice turn.")
        if (
            user_message.session_id != session_id
            or assistant_message.session_id != session_id
            or user_message.thread_id != thread_id
            or assistant_message.thread_id != thread_id
        ):
            raise RuntimeError("Chat messages do not belong to the voice turn's session/thread.")

        revision = self._resolve_revision(
            session_id=session_id,
            requested_revision_id=transcript_revision_id or user_message.transcript_revision_id,
        )
        # Voice mode: the TTS engine fixes the output language (Piper=de, Kokoro=en).
        # We deliberately skip language detection so the model cannot drift into a
        # language the engine cannot pronounce (and then stall on it).
        _, hits, _, model_request = self._retrieve_and_build_request(
            revision=revision,
            user_text=user_message.content_plain_text,
            response_language=engine.language,
            for_speech=True,
        )

        client, model_name = self._resolve_streaming_model_client()
        chunker = SentenceChunker()
        parts: list[str] = []

        def speak(text: str) -> VoiceTurnEvent:
            spoken = _strip_for_speech(text)
            pcm = engine.synthesize_pcm(spoken) if spoken else b""
            # Send the stripped text (not the raw markdown) so the on-screen voice bar
            # shows exactly what is spoken — plain text, never markdown syntax.
            return VoiceTurnEvent(kind="sentence", text=spoken, pcm=pcm)

        # Overlap LLM generation with TTS synthesis: a producer thread drains the model
        # stream into sentence chunks while this generator (the consumer) synthesizes the
        # previous sentence. Synthesizing inline before each yield would stall token
        # generation during synthesis, pushing a turn toward sum(LLM)+sum(TTS).
        sentence_q: queue.Queue = queue.Queue(maxsize=8)
        stop = threading.Event()
        producer_error: list[Exception] = []
        DONE = object()

        def _enqueue(sentence: str) -> None:
            # Wait for room but stay responsive to barge-in (stop) instead of blocking
            # forever on a full queue the consumer has stopped draining.
            while not stop.is_set():
                try:
                    sentence_q.put(sentence, timeout=0.2)
                    return
                except queue.Full:
                    continue

        def produce() -> None:
            try:
                for delta in client.generate_stream(model_request):
                    if stop.is_set():
                        break
                    parts.append(delta)
                    for sentence in chunker.push(delta):
                        _enqueue(sentence)
                else:
                    tail = chunker.flush()
                    if tail:
                        _enqueue(tail)
            except Exception as exc:  # surfaced to the consumer once the queue drains
                producer_error.append(exc)
            finally:
                try:
                    sentence_q.put_nowait(DONE)
                except queue.Full:
                    pass

        producer = threading.Thread(target=produce, name="voice-llm-producer", daemon=True)
        producer.start()
        try:
            while True:
                item = sentence_q.get()
                if item is DONE:
                    break
                yield speak(item)
            # Streaming backend failed before producing anything: spoken fallback, once.
            if producer_error and not parts:
                fallback = RuleBasedChatModelClient().generate(model_request)
                parts.append(fallback.content_markdown)
                model_name = fallback.model_name
                yield speak(fallback.content_markdown)
        finally:
            # Normal end: the producer has already finished. Barge-in (GeneratorExit at a
            # yield): signal stop and drain so a producer parked on a full queue can exit.
            stop.set()
            try:
                while True:
                    sentence_q.get_nowait()
            except queue.Empty:
                pass
            producer.join(timeout=2.0)

        full_markdown = "".join(parts).strip() or "Ich konnte keine Antwort generieren."
        final_markdown, citations = self._validate_and_render_citations(
            raw_markdown=full_markdown, revision=revision, hits=hits, include_footnotes=False
        )
        # Voice answers are plain spoken prose: persist them as plain text (not raw
        # markdown) so the chat bubble and the per-message TTS button match the audio,
        # regardless of whether the model obeyed the no-markdown instruction.
        plain_answer = _markdown_to_plain_text(final_markdown)
        self._store.update_chat_message(
            assistant_message_id,
            content_markdown=plain_answer,
            content_plain_text=plain_answer,
            status="completed",
            model_name=model_name,
            metadata={"retrieval_hit_count": len(hits), "voice_turn": True},
        )
        if citations:
            self._store.create_message_citations(
                message_id=assistant_message_id, citations=citations
            )
        yield VoiceTurnEvent(
            kind="done", assistant_message_id=assistant_message_id, model_name=model_name
        )

    def _retrieve_and_build_request(
        self,
        *,
        revision: TranscriptRevisionRecord | None,
        user_text: str,
        response_language: str | None = None,
        for_speech: bool = False,
    ) -> tuple[Any, list[RetrievalHit], bool, ChatModelRequest]:
        index_info = None
        hits: list[RetrievalHit] = []
        needs_full = False
        # No transcript -> general chat: skip retrieval, leave the context empty.
        if revision is not None:
            index_info = self._retriever.index_revision(revision)
            needs_full = _needs_full_transcript(user_text)
            if needs_full:
                all_chunks, _ = self._retriever.load_chunks_and_vectors(revision=revision)
                ordered = sorted(all_chunks, key=lambda c: c.segment_index)
                # Cap to keep prompt under the LLM context window; ~60 segments of
                # ~30 words is roughly 6k tokens, safely under num_ctx=8192.
                MAX_FULL_SEGMENTS = 60
                if len(ordered) > MAX_FULL_SEGMENTS:
                    ordered = ordered[:MAX_FULL_SEGMENTS]
                hits = [RetrievalHit(chunk=chunk, score=1.0) for chunk in ordered]
            else:
                hits = self._retriever.retrieve(
                    revision=revision,
                    query=user_text,
                    top_k=12,
                    include_neighbors=True,
                )
        model_request = ChatModelRequest(
            user_message=user_text,
            transcript_context=self._format_context_for_model(hits),
            response_language=response_language or self._detect_response_language(user_text),
            for_speech=for_speech,
        )
        return index_info, hits, needs_full, model_request

    def _resolve_streaming_model_client(self) -> tuple[Any, str]:
        if self._model_client is not None and hasattr(self._model_client, "generate_stream"):
            return self._model_client, getattr(self._model_client, "model_label", "custom")
        config = resolve_local_llm_config(store=self._store, settings=self._settings)
        if config.provider == "ollama":
            return OllamaChatModelClient(model_name=config.model_name), "ollama"
        return RuleBasedChatModelClient(), "rule-based-fallback"

    def _resolve_revision(
        self,
        *,
        session_id: str,
        requested_revision_id: str | None,
    ) -> TranscriptRevisionRecord | None:
        if requested_revision_id:
            revision = self._store.get_transcript_revision(requested_revision_id)
            if revision and revision.session_id == session_id:
                return revision
        return self._store.get_latest_transcript_revision_for_session(session_id)

    @staticmethod
    def _format_context_for_model(hits: list[RetrievalHit]) -> str:
        if not hits:
            return ""
        # Present context as bullet lines with explicit segment IDs the model can cite.
        lines: list[str] = []
        for hit in sorted(hits, key=lambda item: item.chunk.segment_index):
            lines.append(
                f"- [{_format_timestamp_ms(hit.chunk.start_ms)}-{_format_timestamp_ms(hit.chunk.end_ms)}] "
                f"({hit.chunk.speaker_name}) [SEG:{hit.chunk.segment_id}] {hit.chunk.text}"
            )
        return "\n".join(lines)

    @staticmethod
    def _detect_response_language(text: str) -> str:
        lowered = text.lower()
        en_tokens = (
            "translate to english",
            "in english",
            "ins englische",
            "summarize in english",
            "english translation",
        )
        if any(token in lowered for token in en_tokens):
            return "en"
        # Heuristic German-vs-English detection (German-first app: ties -> German).
        padded = f" {lowered} "
        de_markers = (
            "ä",
            "ö",
            "ü",
            "ß",
            " der ",
            " die ",
            " das ",
            " und ",
            " ich ",
            " ist ",
            " nicht ",
            " was ",
            " wie ",
            " wir ",
            " sie ",
            " mit ",
            " ein ",
            " auf ",
            " für ",
        )
        en_markers = (
            " the ",
            " is ",
            " and ",
            " you ",
            " what ",
            " how ",
            " are ",
            " with ",
            " this ",
            " that ",
            " can ",
            " please ",
            " of ",
            " to ",
            " a ",
            " do ",
        )
        de = sum(1 for m in de_markers if m in padded)
        en = sum(1 for m in en_markers if m in padded)
        return "en" if en > de else "de"

    def _resolve_model_client(self) -> ChatModelClient:
        if self._model_client is not None:
            return self._model_client
        config = resolve_local_llm_config(store=self._store, settings=self._settings)
        if config.provider == "ollama":
            return OllamaChatModelClient(model_name=config.model_name)
        return RuleBasedChatModelClient()

    def _validate_and_render_citations(
        self,
        *,
        raw_markdown: str,
        revision: TranscriptRevisionRecord | None,
        hits: list[RetrievalHit],
        include_footnotes: bool = True,
    ) -> tuple[str, list[MessageCitationInput]]:
        # No transcript / no retrieval -> general chat: strip any stray markers.
        if revision is None or not hits:
            return _SEGMENT_MARKER_RE.sub("", raw_markdown).strip(), []
        allowed_segment_ids = {hit.chunk.segment_id for hit in hits}
        segments = self._store.list_transcript_segments(revision.id)
        speakers = self._store.list_transcript_speakers(revision.id)
        speaker_map = {speaker.id: speaker for speaker in speakers}
        segment_map = {segment.id: segment for segment in segments}

        cited_segment_ids: list[str] = []

        def _replace(match: re.Match[str]) -> str:
            segment_id = match.group(1)
            if segment_id in allowed_segment_ids and segment_id in segment_map:
                if segment_id not in cited_segment_ids:
                    cited_segment_ids.append(segment_id)
                return ""
            raise CitationValidationError(f"Invalid citation marker for segment {segment_id}")

        try:
            content_without_markers = _SEGMENT_MARKER_RE.sub(_replace, raw_markdown).strip()
        except CitationValidationError:
            # Fallback: drop all markers and citations instead of failing the reply entirely.
            content_without_markers = _SEGMENT_MARKER_RE.sub("", raw_markdown).strip()
            cited_segment_ids = []

        citations: list[MessageCitationInput] = []
        footnotes: list[str] = []
        for idx, segment_id in enumerate(cited_segment_ids, start=1):
            segment = segment_map.get(segment_id)
            if segment is None:
                continue
            speaker_name = "Unknown"
            if segment.speaker_id and segment.speaker_id in speaker_map:
                speaker = speaker_map[segment.speaker_id]
                speaker_name = speaker.display_name or speaker.speaker_key
            citations.append(
                MessageCitationInput(
                    citation_index=idx,
                    segment_id=segment.id,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    quote_excerpt=(segment.text or "")[:240],
                )
            )
            footnotes.append(
                f"[{idx}] {_format_timestamp_ms(segment.start_ms)}-{_format_timestamp_ms(segment.end_ms)} "
                f"({speaker_name})"
            )

        # Voice turns drop the inline footnote text (spoken answers should be plain
        # passages); the structured citation records are still returned and persisted.
        if footnotes and include_footnotes:
            final_markdown = f"{content_without_markers}\n\n" + "\n".join(footnotes)
        else:
            final_markdown = content_without_markers
        return final_markdown.strip(), citations

    def _extract_and_persist_action_proposals(
        self,
        *,
        session_id: str,
        thread_id: str,
        user_message: str,
        assistant_message_id: str,
        assistant_markdown: str,
    ) -> list[str]:
        proposals = self._extract_action_candidates(
            user_message=user_message, assistant_markdown=assistant_markdown
        )
        created_ids: list[str] = []
        for item in proposals:
            created = self._store.create_action_proposal(
                session_id=session_id,
                thread_id=thread_id,
                message_id=assistant_message_id,
                action_type=str(item["action_type"]),
                title=str(item["title"]),
                payload=item["payload"],
                preview_markdown=str(item["preview_markdown"]),
                status="pending",
                requires_confirmation=True,
            )
            created_ids.append(created.id)
        return created_ids

    @staticmethod
    def _extract_action_candidates(
        *,
        user_message: str,
        assistant_markdown: str,
    ) -> list[dict[str, Any]]:
        text = f"{user_message}\n{assistant_markdown}".lower()
        proposals: list[dict[str, Any]] = []
        if "email" in text or "e-mail" in text:
            subject = "Follow-up from meeting"
            body = (
                "Hello,\n\n"
                "Here is the follow-up based on our conversation.\n\n"
                f"{assistant_markdown.strip()}\n\n"
                "Best regards"
            )
            proposals.append(
                {
                    "action_type": "email_draft",
                    "title": "Draft follow-up email",
                    "payload": {
                        "to": "",
                        "subject": subject,
                        "body_markdown": body,
                        "body_text": body,
                    },
                    "preview_markdown": f"**Subject:** {subject}\n\n{body}",
                }
            )
        if "task" in text or "todo" in text:
            tasks = []
            for line in assistant_markdown.splitlines():
                stripped = line.strip().lstrip("-").strip()
                if stripped and not stripped.startswith("["):
                    tasks.append(stripped)
            if not tasks:
                tasks = ["Follow up on transcript action items"]
            proposals.append(
                {
                    "action_type": "task_draft",
                    "title": "Draft task list",
                    "payload": {"tasks": tasks[:10]},
                    "preview_markdown": "\n".join(f"- [ ] {item}" for item in tasks[:10]),
                }
            )
        if "note" in text:
            proposals.append(
                {
                    "action_type": "note_export",
                    "title": "Export meeting note",
                    "payload": {
                        "title": "Meeting Notes",
                        "body_markdown": assistant_markdown,
                    },
                    "preview_markdown": assistant_markdown,
                }
            )
        if any(token in text for token in ("document", "doc ", "report")):
            proposals.append(
                {
                    "action_type": "doc_export",
                    "title": "Export meeting document",
                    "payload": {
                        "title": "Meeting Document",
                        "body_markdown": assistant_markdown,
                    },
                    "preview_markdown": assistant_markdown,
                }
            )
        # Deduplicate by action type in case keywords overlap repeatedly.
        deduped: list[dict[str, Any]] = []
        seen_types: set[str] = set()
        for item in proposals:
            action_type = str(item["action_type"])
            if action_type in seen_types:
                continue
            seen_types.add(action_type)
            deduped.append(item)
        return deduped


def _strip_markdown(text: str) -> str:
    # Minimal plaintext fallback for persisted search/debugging. Not a full markdown parser.
    plain = re.sub(r"\[(\d+)\]\s+[0-9:]+-[0-9:]+\s+\([^)]+\)", "", text)
    plain = plain.replace("## ", "").replace("**", "")
    return re.sub(r"\s+", " ", plain).strip()


_MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")  # [text](url) / ![alt](url) -> text
_CODE_FENCE_RE = re.compile(r"^\s*```.*$", re.MULTILINE)  # ``` fence lines -> drop
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}.*$", re.MULTILINE)  # |---|---| separator rows
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•+]|\d+[.)])\s+", re.MULTILINE)  # bullets & "1." / "1)"
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,;:!?])")


def _strip_for_speech(text: str) -> str:
    """Reduce a chunk to plain spoken text for TTS.

    The model is told not to use markdown, but small local models don't always obey,
    so this is the backstop that guarantees Piper/Kokoro never read raw syntax aloud
    (list numbers, table pipes/dashes, URLs, emphasis markers, citation markers).
    """
    cleaned = _SEGMENT_MARKER_RE.sub("", text)
    cleaned = _MD_LINK_RE.sub(r"\1", cleaned)  # links/images -> visible text, drop URL
    cleaned = _CODE_FENCE_RE.sub("", cleaned)  # drop ``` fence lines
    cleaned = _TABLE_SEP_RE.sub("", cleaned)  # drop |---|---| separator rows
    cleaned = _LIST_MARKER_RE.sub("", cleaned)  # drop leading bullets AND "1."/"1)" per line
    cleaned = cleaned.replace("|", " ")  # remaining table cell pipes -> space
    cleaned = re.sub(r"[*_`#>~]+", " ", cleaned)  # inline emphasis/code/heading/quote/strike
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)  # "code ." -> "code."
    return re.sub(r"\s+", " ", cleaned).strip()


def _markdown_to_plain_text(text: str) -> str:
    """Render a full markdown answer as readable plain text for display/persistence.

    Like :func:`_strip_for_speech` but keeps line breaks (so multi-line answers and
    citation footnotes stay legible in the chat bubble) instead of collapsing them.
    """
    text = _SEGMENT_MARKER_RE.sub("", text)
    text = _MD_LINK_RE.sub(r"\1", text)  # links/images -> visible text, drop URL
    out: list[str] = []
    for line in text.splitlines():
        if _CODE_FENCE_RE.match(line) or _TABLE_SEP_RE.match(line):
            continue  # drop ``` fences and |---|---| separator rows
        line = _LIST_MARKER_RE.sub("", line)  # leading bullets and "1."/"1)"
        line = line.replace("|", " ")  # table cell pipes
        line = re.sub(r"[*_`#>~]+", " ", line)  # emphasis/code/heading/quote/strike
        line = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", line)
        out.append(re.sub(r"[ \t]+", " ", line).strip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
