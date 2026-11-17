from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol

LanguageHint = Literal["auto", "en", "de"]
SttPreset = Literal["fast", "balanced", "quality"]
SttMode = Literal["meeting", "command"]

_LOGGER = logging.getLogger(__name__)
_MEETING_BATCH_SIZE = 8


class SttError(RuntimeError):
    """Base STT error."""


class SttDependencyError(SttError):
    """Raised when `faster-whisper` is not installed."""


class SttConfigError(SttError):
    """Raised when STT settings are invalid."""


@dataclass(frozen=True)
class SttWord:
    text: str
    start_seconds: float | None
    end_seconds: float | None
    probability: float | None = None


@dataclass(frozen=True)
class SttSegment:
    text: str
    start_seconds: float | None
    end_seconds: float | None
    words: tuple[SttWord, ...]
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


@dataclass(frozen=True)
class SttResult:
    text: str
    segments: tuple[SttSegment, ...]
    detected_language: str | None
    detected_language_probability: float | None
    model_name: str
    mode: SttMode
    preset: SttPreset


@dataclass(frozen=True)
class SttResolvedRequest:
    model_name: str
    language: str | None
    beam_size: int
    vad_filter: bool
    word_timestamps: bool
    condition_on_previous_text: bool
    temperature: float
    # Set for long audio: transcribe VAD chunks in parallel batches (~2x CPU, ~4x GPU).
    batch_size: int | None = None


class SpeechToTextClient(Protocol):
    def transcribe_file(
        self,
        audio_path: str | Path,
        *,
        mode: SttMode,
        language_hint: LanguageHint = "auto",
        preset: SttPreset | None = None,
    ) -> SttResult:
        """Transcribe a local audio file."""


def _normalize_language_hint(language_hint: str) -> LanguageHint:
    normalized = language_hint.strip().lower()
    if normalized in {"", "auto"}:
        return "auto"
    if normalized in {"en", "de"}:
        return normalized  # type: ignore[return-value]
    raise SttConfigError("language_hint must be one of: auto, en, de")


def _normalize_preset(preset: str) -> SttPreset:
    normalized = preset.strip().lower()
    if normalized not in {"fast", "balanced", "quality"}:
        raise SttConfigError("preset must be one of: fast, balanced, quality")
    return normalized  # type: ignore[return-value]


def _normalize_mode(mode: str) -> SttMode:
    normalized = mode.strip().lower()
    if normalized not in {"meeting", "command"}:
        raise SttConfigError("mode must be one of: meeting, command")
    return normalized  # type: ignore[return-value]


@lru_cache(maxsize=1)
def _cuda_device_count() -> int:
    """CUDA devices visible to CTranslate2 (faster-whisper's engine); 0 when unavailable."""
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:  # missing package, or a CPU-only build such as the aarch64 wheels
        return 0


def resolve_stt_runtime(
    device: str | None = None, compute_type: str | None = None
) -> tuple[str, str]:
    """Pick `(device, compute_type)`: explicit args, then `TRANSCIBIO_STT_*` env, then auto.

    `auto` means CUDA/float16 when CTranslate2 sees a GPU, else CPU/int8 — e.g. on aarch64
    (DGX Spark / ThinkStation PGX), whose PyPI CTranslate2 wheels are CPU-only.
    """
    resolved_device = (device or os.getenv("TRANSCIBIO_STT_DEVICE") or "auto").strip().lower()
    if resolved_device == "auto":
        resolved_device = "cuda" if _cuda_device_count() > 0 else "cpu"
    resolved_compute_type = (
        compute_type
        or os.getenv("TRANSCIBIO_STT_COMPUTE_TYPE")
        or ("float16" if resolved_device == "cuda" else "int8")
    )
    return resolved_device, resolved_compute_type.strip().lower()


@lru_cache(maxsize=8)
def _load_faster_whisper_model(model_name: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise SttDependencyError(
            "faster-whisper is not installed. Install the vNext dependencies to enable STT."
        ) from exc

    # faster-whisper uses only 4 CPU threads by default; on CPU use every core.
    cpu_threads = (os.cpu_count() or 4) if device == "cpu" else 0
    _LOGGER.info("[STT] Loading faster-whisper '%s' on %s (%s)", model_name, device, compute_type)
    return WhisperModel(
        model_name, device=device, compute_type=compute_type, cpu_threads=cpu_threads
    )


@lru_cache(maxsize=8)
def _load_batched_pipeline(model_name: str, device: str, compute_type: str):
    from faster_whisper import BatchedInferencePipeline

    model = _load_faster_whisper_model(model_name, device=device, compute_type=compute_type)
    return BatchedInferencePipeline(model=model)


class FasterWhisperSttClient:
    """Local STT adapter using `faster-whisper` for both meeting and command audio.

    `device` / `compute_type` default to `resolve_stt_runtime()` (env, then GPU auto-detect).
    """

    def __init__(
        self,
        *,
        device: str | None = None,
        compute_type: str | None = None,
        default_preset: SttPreset = "balanced",
        meeting_model_map: dict[SttPreset, str] | None = None,
        command_model_map: dict[SttPreset, str] | None = None,
    ) -> None:
        self.device = device
        self.compute_type = compute_type
        self.default_preset = _normalize_preset(default_preset)
        self.meeting_model_map = meeting_model_map or {
            "fast": "small",
            "balanced": "medium",
            "quality": "large-v3",
        }
        self.command_model_map = command_model_map or {
            "fast": "small",
            "balanced": "small",
            "quality": "medium",
        }

    def resolve_request(
        self,
        *,
        mode: SttMode,
        language_hint: LanguageHint = "auto",
        preset: SttPreset | None = None,
    ) -> SttResolvedRequest:
        normalized_mode = _normalize_mode(mode)
        normalized_language = _normalize_language_hint(language_hint)
        resolved_preset = self.default_preset if preset is None else _normalize_preset(preset)

        model_map = (
            self.meeting_model_map if normalized_mode == "meeting" else self.command_model_map
        )
        model_name = model_map[resolved_preset]

        # Command STT favors speed and deterministic short transcriptions.
        if normalized_mode == "command":
            return SttResolvedRequest(
                model_name=model_name,
                language=None if normalized_language == "auto" else normalized_language,
                beam_size=1 if resolved_preset == "fast" else 3,
                vad_filter=True,
                word_timestamps=True,
                condition_on_previous_text=False,
                temperature=0.0,
            )

        return SttResolvedRequest(
            model_name=model_name,
            language=None if normalized_language == "auto" else normalized_language,
            beam_size=1 if resolved_preset == "fast" else 5,
            vad_filter=True,
            word_timestamps=True,
            condition_on_previous_text=True,
            temperature=0.0,
            batch_size=_MEETING_BATCH_SIZE,
        )

    def transcribe_file(
        self,
        audio_path: str | Path,
        *,
        mode: SttMode,
        language_hint: LanguageHint = "auto",
        preset: SttPreset | None = None,
    ) -> SttResult:
        path = Path(audio_path)
        if not path.exists():
            raise SttError(f"Audio file not found: {path}")

        normalized_mode = _normalize_mode(mode)
        resolved_preset = self.default_preset if preset is None else _normalize_preset(preset)
        request = self.resolve_request(
            mode=normalized_mode,
            language_hint=language_hint,
            preset=resolved_preset,
        )
        device, compute_type = resolve_stt_runtime(self.device, self.compute_type)
        if request.batch_size is None:
            transcriber = _load_faster_whisper_model(request.model_name, device, compute_type)
            batch_options: dict[str, object] = {}
        else:
            # Segments come back as whole VAD chunks (up to 30 s); transcript assembly splits
            # them into sentences via word timestamps. Don't pass `without_timestamps=False`:
            # it drops short utterances at chunk boundaries (verified on the sample audio).
            transcriber = _load_batched_pipeline(request.model_name, device, compute_type)
            batch_options = {"batch_size": request.batch_size}

        try:
            segments_iter, info = transcriber.transcribe(
                str(path),
                language=request.language,
                task="transcribe",
                beam_size=request.beam_size,
                vad_filter=request.vad_filter,
                word_timestamps=request.word_timestamps,
                condition_on_previous_text=request.condition_on_previous_text,
                temperature=request.temperature,
                **batch_options,
            )
        except Exception as exc:  # pragma: no cover - depends on model runtime
            raise SttError(f"faster-whisper transcription failed: {exc}") from exc

        segments: list[SttSegment] = []
        text_parts: list[str] = []
        for seg in segments_iter:
            seg_text = (getattr(seg, "text", "") or "").strip()
            if seg_text:
                text_parts.append(seg_text)
            words: list[SttWord] = []
            for word in getattr(seg, "words", []) or []:
                words.append(
                    SttWord(
                        text=((getattr(word, "word", "") or "").strip()),
                        start_seconds=getattr(word, "start", None),
                        end_seconds=getattr(word, "end", None),
                        probability=getattr(word, "probability", None),
                    )
                )
            segments.append(
                SttSegment(
                    text=seg_text,
                    start_seconds=getattr(seg, "start", None),
                    end_seconds=getattr(seg, "end", None),
                    words=tuple(words),
                    avg_logprob=getattr(seg, "avg_logprob", None),
                    no_speech_prob=getattr(seg, "no_speech_prob", None),
                )
            )

        detected_language = getattr(info, "language", None)
        detected_language_probability = getattr(info, "language_probability", None)
        full_text = " ".join(part for part in text_parts if part).strip()

        return SttResult(
            text=full_text,
            segments=tuple(segments),
            detected_language=detected_language,
            detected_language_probability=detected_language_probability,
            model_name=request.model_name,
            mode=normalized_mode,
            preset=resolved_preset,
        )

    def transcribe_meeting(
        self,
        audio_path: str | Path,
        *,
        language_hint: LanguageHint = "auto",
        preset: SttPreset | None = None,
    ) -> SttResult:
        return self.transcribe_file(
            audio_path,
            mode="meeting",
            language_hint=language_hint,
            preset=preset,
        )

    def transcribe_command(
        self,
        audio_path: str | Path,
        *,
        language_hint: LanguageHint = "auto",
        preset: SttPreset | None = None,
    ) -> SttResult:
        return self.transcribe_file(
            audio_path,
            mode="command",
            language_hint=language_hint,
            preset=preset,
        )
