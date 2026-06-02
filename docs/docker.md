# Running Transcibio with Docker

A `docker compose up` brings up the whole stack on any machine — no Windows
`.venv` / PowerShell setup required.

```
frontend (nginx)  ->  http://localhost:8080   UI + reverse-proxies /api
backend  (FastAPI/uvicorn)                     internal :8000
Ollama / LM Studio                             reached on the HOST
```

The frontend calls the backend with relative `/api/v1/...` URLs and opens the
voice WebSocket against `window.location.host`, so nginx serves both from a
single origin — no CORS, no baked-in URLs.

## Quick start (GPU)

Requires the **nvidia-container-toolkit** on the host (Linux native, or Windows
via the **WSL2** Docker backend — the Hyper-V backend can't pass through a GPU).

```bash
docker compose up --build
# open http://localhost:8080
```

## CPU-only

No GPU / toolkit? Use the override — it drops the GPU reservation so the stack
still boots (PyTorch's CUDA wheels fall back to CPU, just slower):

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up --build
```

## Local LLM (Ollama / LM Studio)

Run Ollama on the **host** as usual (`ollama serve`, default port `11434`). The
backend reaches it via `host.docker.internal` (already wired in compose). To use
a different model, set `TRANSCIBIO_OLLAMA_MODEL` in a root `.env` file (loaded
automatically). With no LLM running, chat/voice fall back to the deterministic
rule-based replies.

## What's baked vs. mounted

- **Baked into the backend image:** ffmpeg, libsndfile, the Python deps, and
  **both TTS engines** with their models (under `/opt`, outside the volume so the
  bind-mount can't shadow them): **Piper** German (binary + Thorsten voice) and
  **Kokoro** English (`kokoro-onnx` + `kokoro-v1.0.onnx` + `voices-v1.0.bin`).
  Both voice modes work out of the box — pick one in **Settings**.
- **Mounted from `./data` (the volume):** the SQLite DB, session audio, and the
  Hugging Face cache (`faster-whisper` / `pyannote` downloads).
- **`HF_TOKEN`** (for pyannote diarization) goes in the root `.env`.

## Talking to Ollama on the host

The compose file points **all three** Ollama URLs at `host.docker.internal` so the
container reaches Ollama running on your machine: `..._CHAT_URL` and
`..._GENERATE_URL` (replies) plus `..._TAGS_URL` (the Settings panel's model list /
reachability check). If Settings shows "Ollama is not reachable" while chat still
works, the tags URL is the one to check.

## Notes & limits

- GPU passthrough is host-dependent; it is **not** "runs literally anywhere."
  The CPU override is the portable fallback.
- The image targets `linux/amd64` with CUDA `cu128` wheels; the `arm64` branch
  builds CPU-only torch and downloads the aarch64 Piper binary.
