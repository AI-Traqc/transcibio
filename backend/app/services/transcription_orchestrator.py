from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from backend.app.config import AppSettings
from backend.app.services.diarization import (
    DiarizationAttemptResult,
    PyannoteDiarizationClient,
    SafeDiarizationRunner,
)
from backend.app.services.stt import (
    FasterWhisperSttClient,
    LanguageHint,
    SpeechToTextClient,
    SttPreset,
    SttResult,
)
from backend.app.services.stt_nemotron import NemotronTranscriptionEngine
from backend.app.services.transcript_assembly import TranscriptAssemblyService
from backend.app.store import SQLiteStore

TranscriptionEventCallback = Callable[[str, dict[str, Any]], None]

_LOGGER = logging.getLogger(__name__)

# Transcription engines (global setting `stt.engine`). Whisper + pyannote is the default;
# Nemotron 3.5 Transcribe is an optional second engine.
WHISPER_PYANNOTE_ENGINE = "whisper-pyannote"
NEMOTRON_ENGINE = "nemotron"
STT_ENGINES = (WHISPER_PYANNOTE_ENGINE, NEMOTRON_ENGINE)
_SETTINGS_KEY = "privata_vnext_settings"  # same key as the settings router / local_llm.py


def _stored_stt_settings(store: SQLiteStore) -> dict[str, Any]:
    persisted = store.get_app_setting(_SETTINGS_KEY) or {}
    stt = persisted.get("stt") if isinstance(persisted, dict) else None
    return stt if isinstance(stt, dict) else {}


def resolve_stt_engine(store: SQLiteStore) -> str:
    """The engine stored in Settings (`stt.engine`), else the default."""
    engine = _stored_stt_settings(store).get("engine")
    return engine if engine in STT_ENGINES else WHISPER_PYANNOTE_ENGINE


@dataclass(frozen=True)
class SttJobDefaults:
    """Transcription settings from the Settings dialog, applied when a job is queued."""

    engine: str
    preset: SttPreset
    diarization_enabled: bool
    language_hint: LanguageHint


def resolve_stt_job_defaults(store: SQLiteStore, *, default_preset: str) -> SttJobDefaults:
    """Saved `stt.*` settings; `default_preset` (the TRANSCIBIO_PROFILE) when none is saved."""
    stt = _stored_stt_settings(store)
    preset = stt.get("default_preset")
    if preset not in ("fast", "balanced", "quality"):
        preset = default_preset if default_preset in ("fast", "balanced", "quality") else "balanced"
    language = stt.get("default_language_hint")
    diarization = stt.get("diarization_enabled_default")
    return SttJobDefaults(
        engine=resolve_stt_engine(store),
        preset=preset,
        diarization_enabled=diarization if isinstance(diarization, bool) else True,
        language_hint=language if language in ("auto", "en", "de") else "auto",
    )


class TranscriptionEngine(Protocol):
    """Turns one audio file into the `(SttResult, DiarizationAttemptResult)` pair.

    `TranscriptAssemblyService` consumes that pair unchanged, so every engine gets the
    same sentence split, speaker overlap and ≤30 s speaker turns.
    """

    name: str

    def transcribe(
        self,
        audio_path: Path,
        *,
        language_hint: LanguageHint,
        preset: SttPreset,
        diarization_enabled: bool,
        duration_ms: int | None,
        on_stt_complete: Callable[[SttResult], None] | None = None,
    ) -> tuple[SttResult, DiarizationAttemptResult]: ...


class WhisperPyannoteEngine:
    """Today's default: faster-whisper STT, then pyannote diarization (graceful fallback)."""

    name = WHISPER_PYANNOTE_ENGINE

    def __init__(
        self,
        *,
        stt_client: SpeechToTextClient,
        diarization_runner: SafeDiarizationRunner,
        hf_token_env_var: str = "HF_TOKEN",
    ) -> None:
        self._stt_client = stt_client
        self._diarization_runner = diarization_runner
        self._hf_token_env_var = hf_token_env_var

    def transcribe(
        self,
        audio_path: Path,
        *,
        language_hint: LanguageHint,
        preset: SttPreset,
        diarization_enabled: bool,
        duration_ms: int | None,
        on_stt_complete: Callable[[SttResult], None] | None = None,
    ) -> tuple[SttResult, DiarizationAttemptResult]:
        del duration_ms  # no length limit
        stt_started = time.perf_counter()
        stt_result = self._stt_client.transcribe_file(
            audio_path,
            mode="meeting",
            language_hint=language_hint,
            preset=preset,
        )
        _LOGGER.info(
            "[STT] engine=%s model=%s took %.1f s",
            self.name,
            stt_result.model_name,
            time.perf_counter() - stt_started,
        )
        if on_stt_complete is not None:
            on_stt_complete(stt_result)

        diarization_started = time.perf_counter()
        diarization_result = self._diarization_runner.diarize_or_fallback(
            audio_path,
            enabled=diarization_enabled,
            auth_token=os.getenv(self._hf_token_env_var),
        )
        if diarization_enabled:
            _LOGGER.info(
                "[Diarization] used=%s took %.1f s",
                diarization_result.used,
                time.perf_counter() - diarization_started,
            )
        return stt_result, diarization_result


@dataclass(frozen=True)
class TranscriptionJobInput:
    session_id: str
    audio_asset_id: str
    language_hint: LanguageHint = "auto"
    stt_preset: SttPreset = "balanced"
    diarization_enabled: bool = True
    # Read from Settings when the job is queued, so a job keeps the engine it started with.
    stt_engine: str = WHISPER_PYANNOTE_ENGINE


@dataclass(frozen=True)
class TranscriptionJobResult:
    session_id: str
    audio_asset_id: str
    transcript_revision_id: str
    transcript_revision_number: int
    diarization_used: bool
    stt_model: str
    detected_language: str | None
    segment_count: int
    speaker_count: int
    word_count: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TranscriptionOrchestrator:
    """Coordinates audio asset transcription, diarization, and transcript persistence."""

    def __init__(
        self,
        *,
        store: SQLiteStore,
        settings: AppSettings,
        stt_client: SpeechToTextClient,
        diarization_runner: SafeDiarizationRunner,
        transcript_assembly: TranscriptAssemblyService,
        hf_token_env_var: str = "HF_TOKEN",
        extra_engines: Mapping[str, TranscriptionEngine] | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._transcript_assembly = transcript_assembly
        self._engines: dict[str, TranscriptionEngine] = {
            WHISPER_PYANNOTE_ENGINE: WhisperPyannoteEngine(
                stt_client=stt_client,
                diarization_runner=diarization_runner,
                hf_token_env_var=hf_token_env_var,
            ),
            **(extra_engines or {}),
        }

    def transcribe_audio_asset(
        self,
        request: TranscriptionJobInput,
        *,
        on_event: TranscriptionEventCallback | None = None,
    ) -> TranscriptionJobResult:
        session = self._store.get_session(request.session_id)
        if session is None:
            raise ValueError(f"Session not found: {request.session_id}")

        asset = self._store.get_audio_asset(request.audio_asset_id)
        if asset is None:
            raise ValueError(f"Audio asset not found: {request.audio_asset_id}")
        if asset.session_id != request.session_id:
            raise ValueError("Audio asset does not belong to the provided session.")

        audio_path = self._resolve_audio_path(asset.file_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file is missing: {audio_path}")

        engine = self._engines.get(request.stt_engine)
        if engine is None:
            raise ValueError(f"Unknown or unavailable transcription engine: {request.stt_engine}")

        self._emit(
            on_event,
            "transcription.stage",
            {
                "stage": "stt",
                "progress": 0.1,
                "audio_asset_id": request.audio_asset_id,
                "stt_engine": engine.name,
                "message": "Starting speech-to-text transcription",
            },
        )

        def on_stt_complete(stt_result: SttResult) -> None:
            self._emit(
                on_event,
                "transcription.stage",
                {
                    "stage": "stt_complete",
                    "progress": 0.55,
                    "stt_model": stt_result.model_name,
                    "detected_language": stt_result.detected_language,
                    "segment_count": len(stt_result.segments),
                },
            )

        stt_result, diarization_result = engine.transcribe(
            audio_path,
            language_hint=request.language_hint,
            preset=request.stt_preset,
            diarization_enabled=request.diarization_enabled,
            duration_ms=asset.duration_ms,
            on_stt_complete=on_stt_complete,
        )

        self._emit(
            on_event,
            "transcription.stage",
            {
                "stage": "diarization_complete",
                "progress": 0.75,
                "diarization_enabled": request.diarization_enabled,
                "diarization_used": diarization_result.used,
                "speaker_segments": len(diarization_result.segments),
                "warnings": list(diarization_result.warnings),
            },
        )

        assembly_result = self._transcript_assembly.persist_initial_revision(
            session_id=request.session_id,
            stt_result=stt_result,
            diarization=diarization_result,
        )

        self._emit(
            on_event,
            "transcription.stage",
            {
                "stage": "transcript_persisted",
                "progress": 0.98,
                "transcript_revision_id": assembly_result.revision_id,
                "transcript_revision_number": assembly_result.revision_number,
                "segment_count": assembly_result.segment_count,
                "speaker_count": assembly_result.speaker_count,
            },
        )

        return TranscriptionJobResult(
            session_id=request.session_id,
            audio_asset_id=request.audio_asset_id,
            transcript_revision_id=assembly_result.revision_id,
            transcript_revision_number=assembly_result.revision_number,
            diarization_used=assembly_result.diarization_used,
            stt_model=stt_result.model_name,
            detected_language=stt_result.detected_language,
            segment_count=assembly_result.segment_count,
            speaker_count=assembly_result.speaker_count,
            word_count=assembly_result.word_count,
            warnings=assembly_result.warnings,
        )

    def _resolve_audio_path(self, stored_path: str) -> Path:
        path = Path(stored_path)
        if path.is_absolute():
            return path
        return (self._settings.data_root / path).resolve()

    @staticmethod
    def _emit(
        callback: TranscriptionEventCallback | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        if callback is not None:
            callback(event_type, payload)


def build_default_transcription_orchestrator(
    *,
    store: SQLiteStore,
    settings: AppSettings,
) -> TranscriptionOrchestrator:
    stt_client = FasterWhisperSttClient()
    diarization_client = PyannoteDiarizationClient(
        device=os.getenv("TRANSCIBIO_DIARIZATION_DEVICE")
    )
    diarization_runner = SafeDiarizationRunner(diarization_client)
    transcript_assembly = TranscriptAssemblyService(store)
    return TranscriptionOrchestrator(
        store=store,
        settings=settings,
        stt_client=stt_client,
        diarization_runner=diarization_runner,
        transcript_assembly=transcript_assembly,
        # Always registered; it only talks to its server when a job selects it.
        extra_engines={NEMOTRON_ENGINE: NemotronTranscriptionEngine()},
    )
