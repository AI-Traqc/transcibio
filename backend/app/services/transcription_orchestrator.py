from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

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
)
from backend.app.services.transcript_assembly import TranscriptAssemblyService
from backend.app.store import SQLiteStore

TranscriptionEventCallback = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class TranscriptionJobInput:
    session_id: str
    audio_asset_id: str
    language_hint: LanguageHint = "auto"
    stt_preset: SttPreset = "balanced"
    diarization_enabled: bool = True


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
    ) -> None:
        self._store = store
        self._settings = settings
        self._stt_client = stt_client
        self._diarization_runner = diarization_runner
        self._transcript_assembly = transcript_assembly
        self._hf_token_env_var = hf_token_env_var

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

        self._emit(
            on_event,
            "transcription.stage",
            {
                "stage": "stt",
                "progress": 0.1,
                "audio_asset_id": request.audio_asset_id,
                "message": "Starting speech-to-text transcription",
            },
        )
        stt_result = self._stt_client.transcribe_file(
            audio_path,
            mode="meeting",
            language_hint=request.language_hint,
            preset=request.stt_preset,
        )

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

        diarization_auth_token = os.getenv(self._hf_token_env_var)
        diarization_result: DiarizationAttemptResult = self._diarization_runner.diarize_or_fallback(
            audio_path,
            enabled=request.diarization_enabled,
            auth_token=diarization_auth_token,
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
    stt_device = os.getenv("TRANSCIBIO_STT_DEVICE", "cuda")
    stt_compute_type = os.getenv("TRANSCIBIO_STT_COMPUTE_TYPE", "float16")
    stt_client = FasterWhisperSttClient(device=stt_device, compute_type=stt_compute_type)
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
    )
