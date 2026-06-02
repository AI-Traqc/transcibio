# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Transcibio** — on-device assistant for audio transcription, chat over transcripts, voice commands, and action proposals. All processing happens locally. The UI is German-first.

Stack:
- **Backend**: FastAPI + SQLite (`backend/`). Orchestrators for transcription, diarization, chat, actions, TTS. Background job runtime polling SQLite.
- **Frontend**: React + Vite + TypeScript (`frontend/`).
- **Providers** (all optional, with graceful fallbacks): `faster-whisper` (STT), `pyannote.audio` (diarization), Ollama / LM Studio (LLM), Piper (German TTS), Kokoro (English TTS).
- **Streaming voice mode**: hands-free conversational loop (browser VAD → STT → streamed LLM tokens → per-sentence streaming TTS → gapless playback, with barge-in). See the streaming voice flow under Architecture.

## Commands

```bash
# --- Backend (FastAPI) ---
# Install (CPU)
uv pip install --python .venv\Scripts\python.exe ".[dev]"
# Install with CUDA
uv pip install --python .venv\Scripts\python.exe --torch-backend cu128 --reinstall ".[dev]"
# Streaming voice mode deps (Kokoro English TTS)
uv pip install --python .venv\Scripts\python.exe kokoro-onnx soundfile
# Run
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
# Windows helpers
powershell -ExecutionPolicy Bypass -File scripts/start_vnext.ps1
powershell -ExecutionPolicy Bypass -File scripts/check_vnext_env.ps1

# --- Frontend (React + Vite) ---
cd frontend
npm install          # postinstall also runs setup:vad (copies offline VAD assets)
npm run setup:vad    # copy Silero VAD + ONNX Runtime assets into public/vad/ (offline)
npm run dev         # Vite dev server
npm run build       # tsc -b && vite build
npm run test        # Vitest unit/component
npm run test:e2e    # Playwright E2E

# --- Python tests ---
.venv\Scripts\python.exe -m pytest                                     # all
.venv\Scripts\python.exe -m pytest tests/api                           # API routers
.venv\Scripts\python.exe -m pytest tests/services/test_local_llm.py -v # single test file

# --- Lint / format ---
.venv\Scripts\python.exe -m ruff check
.venv\Scripts\python.exe -m ruff check --fix
.venv\Scripts\python.exe -m ruff format
```

Note: prefer invoking the venv Python directly (as above) over `uv run` — `uv run` re-syncs from `uv.lock` and can fail to install transitive wheels for Python 3.10 on Windows.

Voice-mode models (gitignored under `data/`, download separately): the Piper binary at `data/bin/piper/piper.exe`, the Piper German voice `de_DE-thorsten-high.onnx` (+`.json`) under `data/models/tts/piper/`, and Kokoro `kokoro-v1.0.onnx` + `voices-v1.0.bin` under `data/models/tts/kokoro/`. Paths are overridable via env (see Configuration).

## Architecture

**Backend entry** — `backend/app/main.py::create_app()` builds a `FastAPI` instance and, on the `startup` event, wires singletons onto `app.state`: `SQLiteStore`, a transcription orchestrator (`build_default_transcription_orchestrator`), `TranscriptRetriever`, `ChatOrchestrator`, `ActionOrchestrator`, `TtsOrchestrator`, and a `JobRuntime` background worker. All routes are mounted under `/api/v1` via `backend/app/api/router.py`.

**Routers** (`backend/app/api/routers/`): `health`, `sessions`, `transcripts`, `chat`, `voice_commands`, `voice_turn`, `actions`, `jobs`, `settings`, `tts`, `events`. `deps.py` exposes DI helpers that pull orchestrators off `app.state`. `voice_turn` is a WebSocket router (`/api/v1/voice-turn` for full streaming turns, `/api/v1/voice-turn/dev` for engine/latency probing).

**Services** (`backend/app/services/`) — orchestrators that compose smaller providers:
- `transcription_orchestrator.py` + `stt.py`, `diarization.py`, `diarization_pyannote.py`, `transcript_assembly.py`, `transcript_correction.py` — audio → corrected transcript
- `chat_orchestrator.py` + `retrieval.py`, `local_llm.py` — chat with optional transcript-grounded retrieval (blended grounding: transcript when relevant with `[SEG:]` citations, else general knowledge). Also hosts streaming: `StreamingChatModelClient` Protocol, `generate_stream()` on the Ollama (NDJSON) and LM Studio (SSE) clients, and `stream_voice_turn(...)`. For typed chat, reply language matches the user's (`_detect_response_language` DE/EN heuristic). For voice mode the request carries `for_speech=True`, which swaps in a spoken-prose system prompt (plain sentences, no markdown/lists/tables) and **hard-locks the reply language to the TTS engine's** (`engine.language`: Piper=de, Kokoro=en) — no language detection, so the model can't drift into a language the engine can't pronounce.
- `tts_streaming.py` — streaming TTS engines emitting raw int16 mono PCM: `StreamingTtsEngine` Protocol (exposes `name`, `voice`, `sample_rate`, `language`) with `PiperStreamingEngine` (German, Piper binary `--output_raw`, 22.05 kHz; `language` read from the voice config JSON) and `KokoroStreamingEngine` (English, `kokoro-onnx` in-process, 24 kHz; `language` from its `lang`). The voice turn uses `engine.language` to fix the reply language. `VoiceEngineRegistry` caches built engines; `build_streaming_engine(name, data_root)` resolves model paths from env/defaults.
- `text_chunking.py` — `SentenceChunker`, German-aware sentence chunking with an early first-clause flush to minimize time-to-first-audio; does not split on abbreviations (`z. B.`, `d. h.`) or decimals/ordinals.
- `actions.py` — structured action proposals from chat
- `tts.py` — Piper-backed speech synthesis (with fallback)
- `voice_commands` (router) uses `faster-whisper` when available, else returns editable fallback text
- `audio_storage.py` — session-scoped audio persistence under `sessions_root`
- `job_runtime.py` — background job queue polling `SQLiteStore`

**Storage** — `SQLiteStore` (`backend/app/store.py`) persists sessions, jobs, audio assets, transcript revisions, chat turns, etc. Defaults: DB at `data/privata.db`, session audio at `data/sessions/<id>/audio/`.

**Settings** — `AppSettings` (`backend/app/config.py`) is a frozen dataclass built from env vars (all `TRANSCIBIO_*`), cached by `@lru_cache`. Provider choices (`stt_provider`, `llm_provider`, `tts_provider`) drive which adapters are used. `load_dotenv(override=False)` loads `.env` at startup; existing process env wins.

**Diarization** — `backend/app/services/diarization.py` defines a `DiarizationClient` Protocol and a `SafeDiarizationRunner` that swallows failures to fall back to unknown speakers. The pyannote adapter (`diarization_pyannote.py`) is self-contained: it wraps `pyannote.audio.Pipeline`, handles multiple audio-loading strategies (torchaudio → wave module → ffmpeg conversion), and parses varied annotation shapes. Requires `HF_TOKEN` and accepted model terms on Hugging Face.

**Streaming voice flow** — over the `/api/v1/voice-turn` WebSocket: client sends `{session_id, text, engine, transcript_revision_id?}`; server creates the user+assistant chat messages, then runs `ChatOrchestrator.stream_voice_turn(...)` (retrieval → streamed LLM tokens → `SentenceChunker` → per-sentence TTS PCM; reply language is fixed to `engine.language`) and persists the answer with citations. Wire frames: a `start` JSON frame (`sample_rate`, `voice`, `assistant_message_id`, ...), then alternating `sentence` JSON frames + binary int16 PCM, then a `done` frame (`error` on failure). The non-streaming `generate()` and typed-chat job path are unchanged. Note: warm time-to-first-audio is dominated by the local LLM, not TTS.

**Frontend** (`frontend/src/`) — React 18 + Vite + TypeScript. Entry `main.tsx` → `App.tsx`. Components under `src/components/` (`ActionProposalCard`, `SettingsPanel`, `VoiceCommandControls`, `chat/VoiceModeBar` — the "Sprachmodus" toggle above the composer). Streaming voice mode: `audio/PcmStreamPlayer.ts` (gapless Web Audio playback of streamed PCM, `stop()` for barge-in), `hooks/useVoiceTurn.ts` (drives the voice-turn WS), `hooks/useVadConversation.ts` (continuous hands-free loop with browser Silero VAD via `@ricky0123/vad-web`: listen → STT → spoken answer → listen, with barge-in; while active it owns the mic and the manual command mic is disabled — headphones recommended to avoid loudspeaker self-trigger). The Settings dialog has a "Voice-mode engine" dropdown (Piper-German / Kokoro-English). VAD assets are bundled locally for offline use via `scripts/copy-vad-assets.mjs` (runs on `postinstall` / `npm run setup:vad`, copies the Silero ONNX model + ONNX Runtime `.mjs`/`.wasm` into `frontend/public/vad/`, gitignored). Tests: Vitest unit tests in `src/components/__tests__/` and `src/test/`, Playwright E2E in `frontend/tests/e2e/`.

**Graceful fallbacks** — No LM Studio / Ollama ⇒ chat + transcript correction use deterministic fallbacks (streaming voice turns fall back to a single spoken rule-based reply). No transcript ⇒ chat / voice turns answer as a general assistant (no longer an error). No Piper / Kokoro binary or model ⇒ the voice-turn WS returns an `error` frame; text chat still works. No `faster-whisper` ⇒ voice command API returns editable fallback text. No `HF_TOKEN` ⇒ diarization is skipped with a warning; transcript uses fallback speaker labels.

## Configuration

Environment variables loaded from `.env` (see `.env.example`). Existing process env wins over `.env`.

Core:
- `TRANSCIBIO_DATA_ROOT` (default `data`), `TRANSCIBIO_DB_PATH`, `TRANSCIBIO_SESSIONS_ROOT`
- `TRANSCIBIO_API_HOST` (default `127.0.0.1`), `TRANSCIBIO_API_PORT` (default `8000`)
- `TRANSCIBIO_PROFILE` — `fast` | `balanced` | `quality` (default `balanced`)
- `TRANSCIBIO_STT_PROVIDER` (default `faster-whisper`), `TRANSCIBIO_LLM_PROVIDER` (default `ollama`), `TRANSCIBIO_TTS_PROVIDER` (default `piper`)
- `TRANSCIBIO_REQUIRE_FFMPEG` — if `true`, startup fails when ffmpeg/ffprobe missing

Diarization / LLM:
- `HF_TOKEN` — Hugging Face token for pyannote (required only when diarization is used)
- `FORCE_GPU` — if `true`, pyannote fails fast when CUDA is unavailable
- `TRANSCIBIO_DIARIZATION_DEVICE` — pin the pyannote device (e.g. `cpu`, `cuda:0`)
- `TRANSCIBIO_OLLAMA_MODEL`, `TRANSCIBIO_OLLAMA_CHAT_URL`, `TRANSCIBIO_OLLAMA_GENERATE_URL`, `TRANSCIBIO_OLLAMA_CORRECTION_TIMEOUT_SECONDS`

Streaming voice (model paths; all default under `data/`, read in `tts_streaming.py`):
- `TRANSCIBIO_PIPER_BIN` (default `data/bin/piper/piper.exe`), `TRANSCIBIO_PIPER_MODEL` (default `data/models/tts/piper/de_DE-thorsten-high.onnx`)
- `TRANSCIBIO_KOKORO_MODEL` (default `data/models/tts/kokoro/kokoro-v1.0.onnx`), `TRANSCIBIO_KOKORO_VOICES` (default `data/models/tts/kokoro/voices-v1.0.bin`), `TRANSCIBIO_KOKORO_VOICE` (default `af_sarah`)

The default voice-mode engine is also selectable per request and via the `tts.voice_engine` setting (`piper` | `kokoro`, default `piper`).

## Testing Conventions

- **Fakes over mocks**: tests use simple fake implementations rather than `unittest.mock` — they accept preset data and optional `should_fail` flags.
- **Test layout**: `tests/api/` (FastAPI routers), `tests/services/` (service layer), `tests/presentation/` (end-to-end demo paths that exercise the full app).
- **Assertion style**: plain `assert`.
- **Coverage pattern**: happy path + graceful degradation + validation errors.
- **Frontend**: Vitest for unit/component (`frontend/src/**/__tests__/`), Playwright for E2E (`frontend/tests/e2e/`).
- **CI**: `.github/workflows/ci.yml` runs `ruff check`, `ruff format --check`, and `pytest` (backend; deps via `uv pip install`) plus `tsc -b` and `vitest` (frontend) on every push to `main` and every PR. CI installs only the light deps — the optional ML stack (torch/pyannote/faster-whisper/kokoro) is lazy-imported and faked in tests, so it skips the CUDA wheels. Keep all of these green before pushing.

## Code Conventions

- Python 3.10, line length 100 (ruff enforced)
- Ruff rules: E, F, I (isort), B (bugbear). E501 ignored. FastAPI DI markers (`Depends`/`File`/`Form`/`Query`/…) are registered as `extend-immutable-calls` (`[tool.ruff.lint.flake8-bugbear]`) so B008 doesn't flag them.
- Absolute imports: `from backend.app.services.local_llm import ...`
- Type hints everywhere, `|` union syntax (e.g., `str | None`)
- Service boundaries defined as `typing.Protocol` classes
- Dataclasses prefer `@dataclass(frozen=True)` with `tuple` for sequences
- Warnings are collected in result objects, not raised as exceptions
- Non-fatal failures (diarization, individual chunk work) degrade gracefully

## External Dependencies

- **faster-whisper** — STT, local inference
- **pyannote.audio** — diarization. Requires `HF_TOKEN` and accepted model terms.
- **Ollama / LM Studio** — must be running separately. Backend talks to them via stdlib `urllib`; no OpenAI SDK.
- **Piper** — German streaming TTS; needs the Piper binary + `de_DE-thorsten-high` voice downloaded under `data/` (optional)
- **kokoro-onnx** (+ **soundfile**) — English streaming TTS, in-process ONNX; needs `kokoro-v1.0.onnx` + `voices-v1.0.bin` under `data/` (optional)
- **@ricky0123/vad-web** — browser Silero VAD for hands-free voice mode; assets copied into `frontend/public/vad/` for offline use
- **FFmpeg** — required for MP3 and non-native audio ingest
