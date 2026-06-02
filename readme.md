# Transcibio — Local-first audio transcription & assistant

**Transcibio** is an on-device assistant that transcribes audio, identifies who said what, and drives chat / voice-command workflows against a local LLM. It also offers a hands-free **voice mode** — ask a question out loud and hear the answer spoken back. Everything runs locally; no data leaves the machine. The UI is German-first.

- **Backend**: FastAPI (`backend/app/main.py`) with a background job runtime, SQLite persistence, and orchestrators for transcription, **diarization** (labelling each segment by speaker), chat, actions, and **TTS** (text-to-speech, including streaming TTS for voice mode).
- **Frontend**: React + Vite + TypeScript (`frontend/`). Browser-side voice-activity detection (VAD, via Silero) drives turn-taking in voice mode; the VAD model + ONNX Runtime assets are bundled locally so it works offline.
- **Providers** (all optional, with graceful fallbacks): `faster-whisper` (STT, speech-to-text), `pyannote.audio` (diarization), Ollama / LM Studio (LLM), Piper (German TTS), Kokoro (English TTS).

**Chat works with or without a transcript.** With no transcript it's a general assistant; with a transcript it grounds answers in the transcript (with citations) when relevant and falls back to general knowledge otherwise. The assistant replies in the language you speak or type.

---

## Quickstart (Windows)

> **Platform:** Windows is the primary target — all commands below use Windows paths (`.venv\Scripts\python.exe`) and tools (`copy`, `winget`). On macOS/Linux, adapt the venv path to `.venv/bin/python`, use `cp` instead of `copy`, and install FFmpeg via your package manager.

### Prerequisites

**Required:**

- **Python 3.10** via [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js 18+** / `npm`
- **FFmpeg** in `PATH` (for audio ingest):
  ```bash
  winget install -e --id Gyan.FFmpeg
  ffmpeg -version
  ```
- **Ollama** (or LM Studio) running locally for chat / transcript correction. Transcibio defaults to Ollama at `http://127.0.0.1:11434`. Install Ollama, then pull the default model:
  ```bash
  ollama pull gpt-oss-20b
  ollama serve            # if not already running as a service
  ```
  Use a different model by setting `TRANSCIBIO_OLLAMA_MODEL` in `.env`. Without a running LLM, chat still works but falls back to deterministic stub replies.

**Optional:**

- **Hugging Face token** (`HF_TOKEN`) — only needed if you enable pyannote diarization. Accept the model terms at <https://huggingface.co/pyannote/speaker-diarization-community-1>.
- **NVIDIA GPU / CUDA** — speeds up transcription and diarization (see the CUDA install path below).
- **Voice-mode TTS models** — see [Voice mode](#voice-mode-optional) below.

### 1. Get the code

```bash
git clone https://github.com/ai-traqc/transcibio.git
cd transcibio
```

Run every command below from this repository root (the folder containing `pyproject.toml`).

### 2. Install

```bash
# Create the Python venv
uv python install 3.10
uv venv --python 3.10 .venv

# Install backend deps (CPU)
uv pip install --python .venv\Scripts\python.exe ".[dev]"

# …or with NVIDIA GPU / CUDA wheels instead
uv pip install --python .venv\Scripts\python.exe --torch-backend cu128 --reinstall ".[dev]"

# (CUDA only) verify the torch install is CUDA-enabled
.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"

# Install frontend deps
cd frontend
npm install
cd ..

# Configure environment
copy .env.example .env
# edit .env — at minimum set HF_TOKEN if you want diarization
```

The frontend `npm install` automatically runs a `postinstall` step that copies the Silero VAD model + ONNX Runtime assets into `frontend/public/vad/` (re-run manually with `npm run setup:vad`). This keeps voice mode fully offline.

### 3. Configure environment (`.env`)

All settings are optional and have sensible defaults, so `.env` is only needed to override them. Copy the example file and edit as required:

```bash
copy .env.example .env      # Windows (use `cp .env.example .env` on macOS/Linux)
```

The most commonly set values:

- `HF_TOKEN` — your Hugging Face token, required only if you enable pyannote diarization.
- `TRANSCIBIO_OLLAMA_MODEL` — the Ollama model used for chat (default `gpt-oss-20b`).

See `.env.example` for the full, commented list of variables. `.env` is git-ignored, so your secrets are never committed.

### 4. Run

```bash
# Backend (auto-reload)
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload

# Frontend (separate terminal, from frontend/)
cd frontend
npm run dev
```

Then open the app:

- **Frontend** — the Vite dev server prints a URL, usually <http://localhost:5173>. Open it in your browser; you should see the German-first Transcibio UI.
- **Backend API** — <http://127.0.0.1:8000>, with interactive Swagger docs at <http://127.0.0.1:8000/docs>.

Helper scripts (PowerShell) automate the readiness check and starting both servers:

```powershell
# Readiness check (FFmpeg + local providers) — run this first if something doesn't work
powershell -ExecutionPolicy Bypass -File scripts/check_vnext_env.ps1
# Start both backend + frontend
powershell -ExecutionPolicy Bypass -File scripts/start_vnext.ps1
```

### Health / provider readiness

`GET /api/v1/healthz` reports FFmpeg + provider availability (LM Studio, Ollama, Piper) using best-effort checks.

### Fallbacks when providers are offline

- **No local LLM** (Ollama / LM Studio unavailable): chat and transcript correction fall back to deterministic behavior.
- **No Piper / Kokoro** (binary or models missing): TTS and voice mode return a clear failure status; text chat still works.
- **No `faster-whisper` runtime**: the voice command API returns editable fallback text instead of crashing.

---

## Voice mode (optional)

Voice mode lets you hold a continuous, hands-free spoken conversation: you speak, it transcribes, the answer is streamed back as speech, then it listens again — no push-to-talk per turn, and you can interrupt the assistant by speaking (barge-in). Two TTS engines are selectable in **Settings → "Voice-mode engine"**: **Piper** (German, voice `de_DE-thorsten-high`) and **Kokoro** (English).

> Headphones recommended — loudspeaker echo can self-trigger barge-in.

**Python dependencies for Kokoro (English):**

```bash
uv pip install --python .venv\Scripts\python.exe kokoro-onnx soundfile
```

**Models / binaries** live under `data/` (gitignored) and are downloaded once:

| Engine | File(s) | Source |
| --- | --- | --- |
| Piper binary | `data/bin/piper/piper.exe` | [rhasspy/piper releases](https://github.com/rhasspy/piper/releases) |
| Piper voice (DE) | `data/models/tts/piper/de_DE-thorsten-high.onnx` (+ `.onnx.json`) | HF [`rhasspy/piper-voices`](https://huggingface.co/rhasspy/piper-voices) |
| Kokoro (EN) | `data/models/tts/kokoro/kokoro-v1.0.onnx` and `voices-v1.0.bin` | [thewh1teagle/kokoro-onnx releases](https://github.com/thewh1teagle/kokoro-onnx/releases) |

Optional env overrides (defaults shown above are derived from `TRANSCIBIO_DATA_ROOT`):

- `TRANSCIBIO_PIPER_BIN`, `TRANSCIBIO_PIPER_MODEL`
- `TRANSCIBIO_KOKORO_MODEL`, `TRANSCIBIO_KOKORO_VOICES`, `TRANSCIBIO_KOKORO_VOICE` (default `af_sarah`)

**Usage:** click **Sprachmodus** above the chat composer to start. Pick the engine in Settings to match your language.

> Time-to-first-audio depends on the LLM: with the default `gpt-oss-20b` it's ~2.3s warm; a smaller model is faster.

## Supported audio formats

Uploaded audio files must be `.mp3` or `.wav`. In-browser recordings (`.webm`, `.ogg`, `.m4a`, `.mp4`, `.wav`, `.mp3`) are accepted and normalized to WAV via FFmpeg on ingest.

**Sample files for testing:** the repo ships two example recordings in the project root you can upload to try transcription, diarization, and chat end-to-end:

- `Test_Kunde_Handwerker.wav` — a German customer/craftsman conversation (multi-speaker, exercises diarization).
- `transcibio.mp3` — a shorter MP3 sample.

These are staged demo recordings included intentionally; all other local data lives under `data/` and is gitignored.

---

## Tests

```bash
# Backend (Python)
.venv\Scripts\python.exe -m pytest                          # everything
.venv\Scripts\python.exe -m pytest tests/api                # API router tests
.venv\Scripts\python.exe -m pytest tests/services           # service tests
.venv\Scripts\python.exe -m pytest tests/services/test_local_llm.py -v

# Frontend
cd frontend
npm run test          # Vitest (unit / component)
npm run test:e2e      # Playwright
```

## Lint / format

```bash
.venv\Scripts\python.exe -m ruff check
.venv\Scripts\python.exe -m ruff check --fix
.venv\Scripts\python.exe -m ruff format
```

## Continuous integration

Every push to `main` and every pull request runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

- **Backend** — `ruff check`, `ruff format --check`, and `pytest` (dependencies installed with `uv pip install`).
- **Frontend** — `tsc -b` (typecheck) and `vitest`.

The optional ML stack (`torch`, `pyannote.audio`, `faster-whisper`, Kokoro) is imported lazily and replaced by fakes in the tests, so CI installs only the light runtime + dev tools and skips the multi-GB CUDA wheels. The lint, format, and test commands above mirror exactly what CI enforces — run them before pushing.

---

## Run with Docker (easiest — no Python/Node setup)

If you just want to **use** the app without installing Python, Node, or FFmpeg, Docker runs the whole thing — backend, frontend, and German voice — with one command. It works the same on Windows, macOS, and Linux.

### What you need first

1. **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** installed and running.
   - *Windows + NVIDIA GPU:* use Docker Desktop's **WSL 2** backend and install the NVIDIA container toolkit so the GPU is visible inside containers. No GPU? Use the **CPU** command below instead — it just runs slower.
2. **Ollama running on your computer** (for real AI chat answers). Docker does **not** start it for you:
   ```bash
   ollama serve            # start it (if not already running)
   ollama pull gpt-oss-20b # the default model, one-time download
   ```
   Without Ollama the app still opens and works, but chat gives simple canned replies instead of AI answers.

### Start it

From the project root (the folder with `docker-compose.yml`):

```bash
# With an NVIDIA GPU (faster transcription)
docker compose up --build

# Without a GPU (CPU only)
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up --build
```

The first run takes a while (it downloads ~13 GB of dependencies). When it's ready, open:

👉 **http://localhost:8080**

That's the full app. To stop it, press **Ctrl+C**, then optionally `docker compose down` to remove the containers.

### Good to know

- **Both voice engines work out of the box** — Piper (German) and Kokoro (English), with their models, are built into the image. Pick one in **Settings → "Voice-mode engine"**.
- **Your data is saved** in the `data/` folder on your computer (database, recordings, downloaded models), so it survives restarts.
- **Settings** like `HF_TOKEN` or a different `TRANSCIBIO_OLLAMA_MODEL` go in a `.env` file in the project root — it's picked up automatically.

More detail and troubleshooting: [`docs/docker.md`](docs/docker.md).

---

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — architecture, conventions, and a full command reference.
- [`docs/project_overview.md`](docs/project_overview.md) — project overview.
- [`docs/demo_checklist_v1.md`](docs/demo_checklist_v1.md) — demo walkthrough checklist.

## Lizenz

Der Quellcode dieses Repositories steht unter der [MIT-Lizenz](LICENSE).

Wichtige Hinweise zu Drittkomponenten:

- `openai-whisper` und `pyannote.audio` sind eigenständige Drittprojekte und werden upstream unter MIT bereitgestellt.
- Für die Sprecher-Diarisierung verwendet dieses Projekt zusätzlich das Hugging Face-Modell `pyannote/speaker-diarization-community-1`. Dieses Modell wird nicht mit dem Repository ausgeliefert und ist nicht durch die MIT-Lizenz dieses Repositories abgedeckt.
- Die Modellseite für `pyannote/speaker-diarization-community-1` verlangt einen separaten Hugging Face-Zugriff und listet eigene Lizenz- bzw. Nutzungsbedingungen. Prüfen und akzeptieren Sie diese daher immer selbst, bevor Sie die Diarisierung verwenden oder eigene Distributionen mit eingebundenen Modellen weitergeben.
