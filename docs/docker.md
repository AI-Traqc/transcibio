# Running with Docker

The launchers (`Transcibio.bat`, `Transcibio.command`, `scripts/transcibio.sh`; see the
[README](../readme.md)) run Docker for you. This page explains what they start, for running
Docker by hand.

```
frontend (nginx)   http://localhost:8080   UI, proxies /api to the backend
backend (FastAPI)  :8000
Ollama             runs on the host machine, not in Docker
```

## Compose files

| File | Adds | Used by the launcher on |
|---|---|---|
| `docker-compose.yml` | Backend (with NVIDIA GPU) and frontend | every machine |
| `docker-compose.cpu.yml` | No GPU reservation | machines without an NVIDIA GPU, Mac |
| `docker-compose.linux.yml` | Host network, everything on `127.0.0.1` | Linux |

The launcher detects the machine: an NVIDIA GPU (on
Linux also the `nvidia` Docker runtime from the NVIDIA Container Toolkit) → GPU; otherwise
CPU. If the GPU start fails, it retries without the GPU.

## Start by hand

```bash
cp .env.example .env                 # laptop defaults; see the README for larger machines
ollama pull gemma4:e4b               # the model in .env

# Windows / macOS (Docker Desktop)
docker compose up -d --build                                                   # NVIDIA GPU
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build   # no GPU, Mac

# Linux (Docker Engine)
docker compose -f docker-compose.yml -f docker-compose.linux.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.linux.yml -f docker-compose.cpu.yml up -d --build
```

Open <http://localhost:8080>. Stop with `docker compose down`. The first build downloads
several GB.

## Ollama

Ollama runs on the host (port 11434), so it uses the GPU directly and keeps its models
outside the image. Without Ollama, chat uses simple rule-based replies.

- **Docker Desktop (Windows, macOS):** the containers reach it via `host.docker.internal`;
  all three Ollama URLs (chat, generate, tags) are set in `docker-compose.yml`.
- **Linux:** Ollama listens on `127.0.0.1` only, which containers on Docker's bridge network
  can't reach. `docker-compose.linux.yml` puts both containers on the host network instead,
  so Ollama stays private. Don't set `OLLAMA_HOST=0.0.0.0` instead: that exposes Ollama to
  the network.

## Image contents and data

- **In the image:** FFmpeg, the Python dependencies, Piper (German voice) and Kokoro
  (English voice) with their models, under `/opt`.
- **In `./data` (mounted):** database, session audio, downloaded models (faster-whisper,
  pyannote).
- **In `.env`:** `HF_TOKEN`, model choice and other settings (see `.env.example`).

## Notes

- The app only answers to `localhost`, `127.0.0.1` and `::1` because it has no login.
  To open it by another name or IP, add that name to `TRANSCIBIO_ALLOWED_HOSTS`. The
  microphone then also needs `https://`.
- The generic `Dockerfile` targets `linux/amd64` with CUDA 12.8. On other ARM machines it
  installs CPU-only PyTorch.
- nginx uses `frontend/nginx.conf.template` (`NGINX_LISTEN`, default `80`;
  `BACKEND_UPSTREAM`, default `backend:8000`). Uploads up to 2 GB are allowed.
