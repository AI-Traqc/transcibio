# syntax=docker/dockerfile:1
#
# vLLM server for NVIDIA Nemotron 3.5 Transcribe: an optional
# second transcription engine next to Whisper + pyannote.
# Built and started only with the compose profile `nemotron` (docker-compose.spark.yml).
#
# Follows the model card's environment (vLLM 0.32.0 + NeMo Speech main, Python 3.13).
# CUDA 13 *devel* base: FlashInfer JIT-compiles the quantized kernels at first start and needs
# nvcc. Same image as the CTranslate2 build stage in Dockerfile.spark (shared layers).
# Weights are NOT baked in: they live in the mounted data/models/nemotron/.

ARG CUDA_VERSION=13.0.3

FROM ghcr.io/astral-sh/uv:0.13.8 AS uv

FROM nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu24.04

# NeMo Speech has no release with the vLLM plugin yet; pin the main commit that was tested.
ARG NEMO_SPEECH_COMMIT=eaf0098ddeffb804ef1b1fb3a955b3bf022f4171

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl ffmpeg libsndfile1 build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/nemo-speech/.venv

RUN git clone https://github.com/NVIDIA-NeMo/Speech.git /opt/nemo-speech \
    && git -C /opt/nemo-speech checkout ${NEMO_SPEECH_COMMIT}
WORKDIR /opt/nemo-speech

# Model card recipe: locked deps with the asr + vllm extras, NeMo itself editable without
# deps, PyAV for compressed audio, and OpenCV (vLLM needs it; NeMo's settings exclude it).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv --python 3.13 /opt/nemo-speech/.venv \
    && uv sync --extra asr --extra vllm --locked --no-install-project \
    && uv pip install --python .venv/bin/python --no-deps -e . \
    && uv pip install --python .venv/bin/python --no-deps av==19.0.2 opencv-python-headless==5.0.0.93

ENV VIRTUAL_ENV=/opt/nemo-speech/.venv \
    PATH=/opt/nemo-speech/.venv/bin:/usr/local/cuda/bin:$PATH \
    VLLM_PLUGINS=nemo_speechlm \
    VLLM_USE_V2_MODEL_RUNNER=0 \
    VLLM_DISABLED_KERNELS=FlashInferFP8ScaledMMLinearKernel \
    VLLM_MAX_AUDIO_DECODE_DURATION_S=3600 \
    VLLM_MAX_AUDIO_CLIP_FILESIZE_MB=180 \
    HF_HOME=/models/.hf \
    FLASHINFER_WORKSPACE_BASE=/models/.flashinfer

# Fail the build early if the stack doesn't import on this platform.
RUN python -c "import vllm, torch, nemo; print('vllm', vllm.__version__, 'torch', torch.__version__, 'cuda', torch.version.cuda)"

EXPOSE 8010
# The serve command (FP8 profile) lives in docker-compose.spark.yml.
