# Architecture

Transcibio is a local web app: a React frontend, a FastAPI backend with SQLite, and local AI
models. Nothing leaves the machine.

```
Browser (React + Vite)
  │  REST /api/v1/*  ·  WebSocket /api/v1/voice-turn  ·  SSE events
  ▼
Backend (FastAPI)
  ├─ API routers ─────────── sessions, transcripts, chat, voice, actions, settings, jobs
  ├─ Services ────────────── transcription, chat, actions, TTS (orchestrators)
  ├─ Job runtime ─────────── background worker for transcription and chat jobs
  └─ Storage ─────────────── SQLite (data/privata.db) + files (data/sessions/<id>/)
  │
  ▼
Local models
  ├─ Speech-to-text ──────── faster-whisper, or Nemotron 3.5 Transcribe (own vLLM server)
  ├─ Speaker detection ───── pyannote (with Whisper); built into Nemotron
  ├─ Language model ──────── Ollama (chat, transcript correction, titles)
  └─ Text-to-speech ──────── Piper (German), Kokoro (English)
```

## Backend

`backend/app/main.py::create_app()` builds the FastAPI app and, at startup, puts the shared
services on `app.state`. All routes live under `/api/v1` (`backend/app/api/router.py`).
`LocalOnlyMiddleware` rejects requests whose `Host` or `Origin` isn't local (the app has no
login; see `TRANSCIBIO_ALLOWED_HOSTS`).

### Services (`backend/app/services/`)

| Module | Role |
|---|---|
| `transcription_orchestrator.py` | Runs a transcription engine, then `transcript_assembly.py`, and stores a transcript revision. |
| `stt.py` | faster-whisper (`BatchedInferencePipeline` for meetings, sequential for voice commands). Device auto-detect: CUDA if CTranslate2 sees a GPU, else CPU. |
| `diarization.py`, `diarization_pyannote.py` | Speaker detection with pyannote; failures fall back to "unknown speaker". |
| `whisper_prefetch.py` | Downloads every Whisper model the presets use (small, medium, large-v3); the launchers run it in the backend container on each start, cached models are skipped. |
| `stt_nemotron.py` | Optional engine: one request to a Nemotron vLLM server returns text, word timestamps and speakers. |
| `transcript_assembly.py` | Splits text into sentences, assigns each the overlapping speaker, merges them into speaker turns of at most 30 s. |
| `chat_orchestrator.py` | Retrieval, prompt, LLM call (typed or streamed), citations; streaming voice turns. |
| `retrieval.py` | Keyword (sparse vector) search over transcript segments. |
| `app_context.py` | Short self-description of the app and its current models, added to every chat prompt. |
| `text_chunking.py` | Splits streamed LLM text into sentences for speech. |
| `tts_streaming.py`, `tts.py` | Piper and Kokoro speech output. |
| `actions.py` | Action proposals from chat (e.g. email drafts) and their execution. |
| `local_llm.py` | Resolves the chat model, thinking mode and context size from Settings and env. |
| `job_runtime.py` | Background queue for transcription and chat jobs, stored in SQLite. |

### Transcription engines

The engine is a global setting (`stt.engine`) and applies to uploads, recordings and voice
input. Both engines return the same `(SttResult, DiarizationAttemptResult)` pair, so the
assembly step is shared.

| Engine | Text | Speakers | Runs as |
|---|---|---|---|
| `whisper-pyannote` (default) | faster-whisper: `small` / `medium` / `large-v3` (Fast / Balanced / Quality) | pyannote `speaker-diarization-community-1` | in the backend |
| `nemotron` | NVIDIA Nemotron 3.5 Transcribe | from the same request | separate vLLM server (`docker/nemotron/`) |

A job records the engine, preset, speaker setting and language when it's queued, so a change
in Settings doesn't affect running jobs. There is no fallback between engines: if Nemotron is
selected and its server is down, the job fails with a clear message.

The Nemotron server needs about 5 minutes to load and warm up before it answers. Its container
runs vLLM through `docker/nemotron/serve.sh`, which refreshes `data/models/nemotron/.server-status.json`
every 5 s while the process lives. `GET /api/v1/settings/nemotron-status` reports `running`
(the server answers), `starting` (fresh heartbeat, no answer yet) or `stopped`; the Settings
dialog polls it until the server runs.

### Chat

1. Retrieval picks the most relevant transcript segments (or the whole transcript for
   summaries), within a token budget.
2. The prompt contains the app description, the transcript lines with short source numbers
   (`- [S3] mm:ss–mm:ss, Speaker: text`) and the question.
3. The answer cites sources as `[S3]`. The backend maps them to transcript segments, turns
   them into numbered citations, and removes every marker from the shown and spoken text.

Thinking mode (Settings) applies to typed chat and transcript correction; voice turns never
think. Every Ollama call uses the same context size, so Ollama doesn't reload the model.

### Voice mode

Over the `/api/v1/voice-turn` WebSocket: the browser detects speech (Silero VAD), the
backend transcribes it, streams the LLM answer, splits it into sentences and sends each
sentence as text plus raw audio (PCM). The browser plays the audio gaplessly and stops when
the user speaks again (barge-in). The reply language is fixed to the voice (Piper: German,
Kokoro: English).

## Frontend (`frontend/src/`)

React 18 + TypeScript + Vite. `App.tsx` holds the layout; components live in
`components/`, API calls in `api/`, hooks in `hooks/` (`useVoiceTurn`, `useVadConversation`
for voice mode). The Settings dialog has three groups: Transcription, Chat, Voice. In Docker,
nginx serves the built app and proxies `/api` to the backend
(`frontend/nginx.conf.template`).

## Storage

- `data/privata.db`: sessions, audio assets, transcript revisions (every edit creates a new
  revision), chat messages, citations, actions, jobs, settings.
- `data/sessions/<id>/audio/`: uploaded and recorded audio. `data/sessions/<id>/exports/`:
  action outputs.
- `data/models/`, `data/.hf_cache/`: downloaded models.

## Fallbacks

| Missing | Behavior |
|---|---|
| Ollama | Chat and correction use simple rule-based replies. |
| `HF_TOKEN` / pyannote | Transcript without speaker labels. |
| Piper / Kokoro | Voice mode reports an error; text chat works. |
| faster-whisper | Voice commands return editable placeholder text. |

## Deployment

- **Development:** `node start.mjs` (backend + Vite dev server), see `docs/development.md`.
- **Docker (users):** the launcher (`scripts/transcibio.sh`, `scripts/transcibio.ps1`, started
  by `Transcibio.bat` / `Transcibio.command` or the Linux icon) picks the compose files for the
  machine: `docker-compose.yml` plus `docker-compose.cpu.yml` (no GPU),
  or `docker-compose.linux.yml` (Linux host network). See `docs/docker.md`.
