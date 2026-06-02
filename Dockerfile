# syntax=docker/dockerfile:1

# Use uv binary from the official image
FROM ghcr.io/astral-sh/uv:0.8.15 AS uv

# Multi-arch base image (BuildKit injects the right platform by default)
FROM python:3.10-slim

ARG TARGETPLATFORM
ARG BUILDPLATFORM
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# System dependencies (ffmpeg for audio, libsndfile for pyannote/kokoro,
# git for some wheels, curl/ca-certificates to fetch the Piper assets).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        git \
        curl \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- Piper German TTS (binary + Thorsten voice) ---------------------------------
# Installed under /opt/piper, i.e. OUTSIDE the mounted /app/data volume, so the
# bind-mount does not shadow it. The release tarball ships the binary together
# with its $ORIGIN-rpath libs and espeak-ng-data, so no LD_LIBRARY_PATH needed.
ARG PIPER_RELEASE=2023.11.14-2
ARG PIPER_VOICE_BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/high
RUN set -eux; \
    case "$TARGETPLATFORM" in \
      "linux/arm64") PIPER_ARCH=linux_aarch64 ;; \
      *)             PIPER_ARCH=linux_x86_64 ;; \
    esac; \
    curl -fsSL "https://github.com/rhasspy/piper/releases/download/${PIPER_RELEASE}/piper_${PIPER_ARCH}.tar.gz" \
      | tar -xz -C /opt; \
    curl -fsSL "${PIPER_VOICE_BASE}/de_DE-thorsten-high.onnx"      -o /opt/piper/de_DE-thorsten-high.onnx; \
    curl -fsSL "${PIPER_VOICE_BASE}/de_DE-thorsten-high.onnx.json" -o /opt/piper/de_DE-thorsten-high.onnx.json

# --- Kokoro English TTS (model + voice vectors) ---------------------------------
# Also under /opt (outside the mounted /app/data volume). The kokoro-onnx Python
# package is installed below; here we fetch the model weights + voice vectors so
# English voice mode works out of the box.
ARG KOKORO_RELEASE=model-files-v1.0
ARG KOKORO_BASE=https://github.com/thewh1teagle/kokoro-onnx/releases/download
RUN set -eux; \
    mkdir -p /opt/kokoro; \
    curl -fsSL "${KOKORO_BASE}/${KOKORO_RELEASE}/kokoro-v1.0.onnx" -o /opt/kokoro/kokoro-v1.0.onnx; \
    curl -fsSL "${KOKORO_BASE}/${KOKORO_RELEASE}/voices-v1.0.bin"  -o /opt/kokoro/voices-v1.0.bin

ENV TRANSCIBIO_PIPER_BIN=/opt/piper/piper \
    TRANSCIBIO_PIPER_MODEL=/opt/piper/de_DE-thorsten-high.onnx \
    TRANSCIBIO_KOKORO_MODEL=/opt/kokoro/kokoro-v1.0.onnx \
    TRANSCIBIO_KOKORO_VOICES=/opt/kokoro/voices-v1.0.bin \
    # Persist Hugging Face downloads (faster-whisper / pyannote) into the data
    # volume instead of an ephemeral container layer.
    HF_HOME=/app/data/.hf_cache

WORKDIR /app
COPY --from=uv /uv /uvx /bin/

# Install Python deps first (better layer caching). Only the backend package and
# its metadata are needed to build/install — model weights stay in the volume.
COPY pyproject.toml ./
COPY backend ./backend

# The uv cache is mounted so editing backend code (which invalidates this layer)
# reuses already-downloaded wheels instead of re-pulling the multi-GB CUDA stack.
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$TARGETPLATFORM" = "linux/arm64" ]; then \
        uv pip install --system .; \
    else \
        uv pip install --system --torch-backend cu128 --reinstall .; \
    fi

# Streaming English TTS (in-process ONNX). Installed separately so it doesn't
# perturb the torch backend resolution above.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system kokoro-onnx soundfile

EXPOSE 8000

# Bind to 0.0.0.0 so the frontend container (and host) can reach the API.
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
