"""Voice-turn WebSockets.

``/api/v1/voice-turn`` runs a full streaming turn: it creates the chat messages
(mirroring POST /chat/messages), then streams the answer as LLM tokens are
chunked into sentences, each synthesized to PCM and pushed to the browser while
the next sentence is still being generated. Protocol:

  client -> {"session_id", "text", "engine", "voice"?, "transcript_revision_id"?}
  server -> {"type":"start", sample_rate, voice, assistant_message_id, ...}
  server -> {"type":"sentence", "text": "..."}  followed by raw int16 PCM frames
  server -> {"type":"done", "assistant_message_id", "model_name"}
  server -> {"type":"error", "message"} on failure

``/api/v1/voice-turn/dev`` is the original vertical-slice probe (hardcoded text,
no chat persistence) kept for engine/latency testing.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import AsyncIterator, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.services.chat_orchestrator import VoiceTurnEvent
from backend.app.services.tts_streaming import (
    StreamingTtsError,
    StreamingTtsUnavailable,
    VoiceEngineRegistry,
)

router = APIRouter()

# ~46 ms of audio per frame at 22 kHz / ~42 ms at 24 kHz; even byte count keeps
# int16 samples aligned across the WebSocket boundary.
_FRAME_BYTES = 8192

_DEFAULT_TEXT = {
    "piper": "Guten Tag! Dies ist eine Demonstration des lokalen Sprachmodus.",
    "kokoro": "Good afternoon! This is a demonstration of the local voice mode.",
}

_SENTINEL = object()


def _get_registry(ws: WebSocket) -> VoiceEngineRegistry:
    registry = getattr(ws.app.state, "voice_engines", None)
    if registry is None:
        registry = VoiceEngineRegistry(ws.app.state.settings.data_root)
        ws.app.state.voice_engines = registry
    return registry


async def _safe_send_json(ws: WebSocket, payload: dict[str, object]) -> None:
    try:
        await ws.send_json(payload)
    except (WebSocketDisconnect, RuntimeError):
        pass


async def _bridge_sync_gen(factory: Callable[[], object]) -> AsyncIterator[object]:
    """Run a blocking sync generator in a thread, yielding its items on the loop.

    When the consumer stops early (barge-in or client disconnect), ``cancelled`` is
    set so the worker stops pulling from the source generator after at most one more
    item instead of running the whole LLM+TTS turn to completion in the background.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    cancelled = threading.Event()

    def worker() -> None:
        gen = factory()
        try:
            for item in gen:  # type: ignore[attr-defined]
                if cancelled.is_set():
                    break
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as exc:  # surface to the socket as an error event
            loop.call_soon_threadsafe(queue.put_nowait, ("__error__", exc))
        finally:
            close = getattr(gen, "close", None)
            if callable(close):
                close()  # let the source generator release any resources (TTS, HTTP)
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    future = loop.run_in_executor(None, worker)
    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            yield item
    finally:
        cancelled.set()
        await future


@router.websocket("/voice-turn")
async def voice_turn(ws: WebSocket) -> None:
    await ws.accept()
    try:
        raw = await ws.receive_text()
    except WebSocketDisconnect:
        return
    try:
        request = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        await _safe_send_json(ws, {"type": "error", "message": "Invalid request payload."})
        await ws.close()
        return

    session_id = str(request.get("session_id") or "")
    text = str(request.get("text") or "").strip()
    engine_name = str(request.get("engine") or "piper").lower()
    revision_id = request.get("transcript_revision_id")
    revision_id = str(revision_id) if revision_id else None

    if not session_id or not text:
        await _safe_send_json(ws, {"type": "error", "message": "session_id and text are required."})
        await ws.close()
        return

    store = ws.app.state.store
    orchestrator = ws.app.state.chat_orchestrator

    session = store.get_session(session_id)
    if session is None:
        await _safe_send_json(ws, {"type": "error", "message": "Session not found."})
        await ws.close()
        return

    # Transcript is optional: grounded when present, general chat when absent.
    revision = None
    if revision_id:
        candidate = store.get_transcript_revision(revision_id)
        if candidate is not None and candidate.session_id == session_id:
            revision = candidate
    if revision is None:
        revision = store.get_latest_transcript_revision_for_session(session_id)
    revision_id = revision.id if revision else None

    try:
        engine = await asyncio.to_thread(_get_registry(ws).get, engine_name)
    except (StreamingTtsUnavailable, StreamingTtsError) as exc:
        await _safe_send_json(ws, {"type": "error", "message": str(exc)})
        await ws.close()
        return

    thread = store.get_or_create_chat_thread(session_id=session_id)
    user_message = store.create_chat_message(
        thread_id=thread.id,
        session_id=session_id,
        transcript_revision_id=revision_id,
        role="user",
        content_markdown=text,
        content_plain_text=text,
        source_kind="voice_command",
        status="completed",
    )
    assistant = store.create_chat_message(
        thread_id=thread.id,
        session_id=session_id,
        transcript_revision_id=revision_id,
        role="assistant",
        content_markdown="",
        content_plain_text="",
        source_kind="assistant_reply",
        status="running",
        metadata={"pending": True, "voice_turn": True},
    )

    await ws.send_json(
        {
            "type": "start",
            "engine": engine.name,
            "voice": engine.voice,
            "sample_rate": engine.sample_rate,
            "format": "pcm_s16le",
            "channels": 1,
            "thread_id": thread.id,
            "user_message_id": user_message.id,
            "assistant_message_id": assistant.id,
        }
    )

    def produce() -> object:
        return orchestrator.stream_voice_turn(
            session_id=session_id,
            thread_id=thread.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant.id,
            engine=engine,
            transcript_revision_id=revision_id,
        )

    try:
        async for event in _bridge_sync_gen(produce):
            if isinstance(event, tuple) and event and event[0] == "__error__":
                store.update_chat_message(assistant.id, status="failed")
                await _safe_send_json(ws, {"type": "error", "message": str(event[1])})
                break
            assert isinstance(event, VoiceTurnEvent)
            if event.kind == "sentence":
                await _safe_send_json(ws, {"type": "sentence", "text": event.text})
                for offset in range(0, len(event.pcm), _FRAME_BYTES):
                    await ws.send_bytes(event.pcm[offset : offset + _FRAME_BYTES])
            elif event.kind == "done":
                await _safe_send_json(
                    ws,
                    {
                        "type": "done",
                        "assistant_message_id": event.assistant_message_id,
                        "model_name": event.model_name,
                    },
                )
    except WebSocketDisconnect:
        return
    await ws.close()


@router.websocket("/voice-turn/dev")
async def voice_turn_dev(ws: WebSocket) -> None:
    await ws.accept()
    try:
        raw = await ws.receive_text()
    except WebSocketDisconnect:
        return

    try:
        request = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        request = {}
    engine_name = str(request.get("engine") or "piper").lower()
    text = str(request.get("text") or _DEFAULT_TEXT.get(engine_name, _DEFAULT_TEXT["piper"]))

    started = time.perf_counter()
    try:
        engine = await asyncio.to_thread(_get_registry(ws).get, engine_name)
        pcm = await asyncio.to_thread(engine.synthesize_pcm, text)
    except (StreamingTtsUnavailable, StreamingTtsError) as exc:
        await _safe_send_json(ws, {"type": "error", "message": str(exc)})
        await ws.close()
        return

    ttfa_ms = (time.perf_counter() - started) * 1000.0
    await ws.send_json(
        {
            "type": "start",
            "engine": engine.name,
            "voice": engine.voice,
            "sample_rate": engine.sample_rate,
            "format": "pcm_s16le",
            "channels": 1,
            "text": text,
        }
    )

    frames = 0
    for offset in range(0, len(pcm), _FRAME_BYTES):
        await ws.send_bytes(pcm[offset : offset + _FRAME_BYTES])
        frames += 1

    audio_ms = (len(pcm) / 2) / max(1, engine.sample_rate) * 1000.0
    await _safe_send_json(
        ws,
        {
            "type": "done",
            "frames": frames,
            "pcm_bytes": len(pcm),
            "ttfa_ms": round(ttfa_ms, 1),
            "audio_ms": round(audio_ms, 1),
        },
    )
    await ws.close()
