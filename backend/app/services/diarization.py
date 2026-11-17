from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class DiarizationError(RuntimeError):
    """Base diarization error."""


class DiarizationDependencyError(DiarizationError):
    """Raised when pyannote dependencies are unavailable."""


class DiarizationConfigError(DiarizationError):
    """Raised for invalid diarization configuration."""


@dataclass(frozen=True)
class DiarizationSpeakerSegment:
    start_seconds: float
    end_seconds: float
    speaker_key: str


@dataclass(frozen=True)
class DiarizationAttemptResult:
    segments: tuple[DiarizationSpeakerSegment, ...]
    used: bool
    warnings: tuple[str, ...] = ()
    provider: str = "pyannote"


class DiarizationClient(Protocol):
    def diarize_file(
        self,
        audio_path: str | Path,
        *,
        auth_token: str | None = None,
    ) -> tuple[DiarizationSpeakerSegment, ...]:
        """Return normalized diarization speaker segments."""


class PyannoteDiarizationClient:
    """Thin wrapper over the pyannote diarizer in ``diarization_pyannote``."""

    def __init__(
        self,
        *,
        pipeline_name: str | None = None,
        device: str | None = None,
    ) -> None:
        self.pipeline_name = pipeline_name
        self.device = device

    def diarize_file(
        self,
        audio_path: str | Path,
        *,
        auth_token: str | None = None,
    ) -> tuple[DiarizationSpeakerSegment, ...]:
        path = Path(audio_path)
        if not path.exists():
            raise DiarizationError(f"Audio file not found: {path}")

        try:
            from backend.app.services.diarization_pyannote import PyannoteDiarizer
        except Exception as exc:  # pragma: no cover - environment dependent
            raise DiarizationDependencyError(f"Failed to import pyannote diarizer: {exc}") from exc

        try:
            if self.pipeline_name is not None:
                diarizer = PyannoteDiarizer(pipeline_name=self.pipeline_name, device=self.device)
            else:
                diarizer = PyannoteDiarizer(device=self.device)
            raw_segments = diarizer.diarize(str(path), auth_token=auth_token)
        except Exception as exc:  # pragma: no cover - model runtime dependent
            raise DiarizationError(f"Pyannote diarization failed: {exc}") from exc

        normalized = []
        for seg in raw_segments:
            start = float(seg.start)
            end = float(seg.end)
            speaker = str(getattr(seg, "speaker", "UNKNOWN_SPEAKER"))
            if end <= start:
                continue
            normalized.append(
                DiarizationSpeakerSegment(
                    start_seconds=max(0.0, start),
                    end_seconds=max(0.0, end),
                    speaker_key=speaker,
                )
            )
        normalized.sort(key=lambda item: (item.start_seconds, item.end_seconds, item.speaker_key))
        return tuple(normalized)


class SafeDiarizationRunner:
    """Runs diarization with graceful fallback to no-speaker labels."""

    def __init__(self, client: DiarizationClient) -> None:
        self._client = client

    def diarize_or_fallback(
        self,
        audio_path: str | Path,
        *,
        enabled: bool = True,
        auth_token: str | None = None,
    ) -> DiarizationAttemptResult:
        if not enabled:
            return DiarizationAttemptResult(
                segments=(),
                used=False,
                warnings=("Diarization disabled; transcript will use unknown speakers.",),
            )

        try:
            segments = self._client.diarize_file(audio_path, auth_token=auth_token)
            return DiarizationAttemptResult(
                segments=segments,
                used=bool(segments),
                warnings=() if segments else ("Diarization returned no speaker segments.",),
            )
        except Exception as exc:
            return DiarizationAttemptResult(
                segments=(),
                used=False,
                warnings=(f"Diarization failed and was skipped: {exc}",),
            )
