# Development setup

For working on the code. To just use the app, see the [README](../readme.md).

Commands are shown for Windows. On Linux/macOS use `.venv/bin/python` and `cp`.

## Requirements

- Python 3.10 via [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js 18+
- FFmpeg on `PATH` (`winget install -e --id Gyan.FFmpeg`)
- Ollama with the chat model from `.env` (`ollama pull gemma4:e4b`; see the README for larger machines)
- Optional: NVIDIA GPU, a Hugging Face token for speaker detection

## Install

```bash
uv python install 3.10
uv venv --python 3.10 .venv

# Backend: CPU …
uv pip install --python .venv\Scripts\python.exe ".[dev]"
# … or NVIDIA GPU (CUDA wheels)
uv pip install --python .venv\Scripts\python.exe --torch-backend cu128 --reinstall ".[dev]"

# English voice (Kokoro)
uv pip install --python .venv\Scripts\python.exe kokoro-onnx soundfile

# Frontend (postinstall copies the offline voice-detection assets into public/vad/)
cd frontend && npm install && cd ..

copy .env.example .env
```

Prefer calling the venv Python directly over `uv run`, which re-syncs from `uv.lock`.

Optional: download all Whisper models now instead of on first use (about 5 GB):
`.venv\Scripts\python.exe -m backend.app.services.whisper_prefetch`.

Voice models are not in the repo. Put them under `data/` (or point the env vars in
`.env.example` elsewhere):

| Engine | Files |
|---|---|
| Piper (German) | `data/bin/piper/piper.exe`, `data/models/tts/piper/de_DE-thorsten-high.onnx` (+ `.json`) |
| Kokoro (English) | `data/models/tts/kokoro/kokoro-v1.0.onnx`, `voices-v1.0.bin` |

## Run

```bash
node start.mjs          # backend :8000 + frontend :5173, Ctrl+C stops both
```

Or separately: `.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload` and
`npm run dev` in `frontend/`. API docs: <http://127.0.0.1:8000/docs>. Readiness check
(Windows): `powershell -ExecutionPolicy Bypass -File scripts/check_vnext_env.ps1`.

## Test and lint

```bash
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check
.venv\Scripts\python.exe -m ruff format

cd frontend
npm run test            # Vitest
npx tsc -b              # type check
npm run test:e2e        # Playwright
```

CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check`, `pytest`, `tsc -b`
and `vitest` on every push to `main` and every pull request. The ML libraries (torch,
pyannote, faster-whisper, Kokoro) are imported lazily and faked in tests, so CI installs only
the light dependencies.
