from __future__ import annotations

import json
import os
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from backend.app.config import AppSettings
from backend.app.store import AudioAssetRecord, ChatMessageRecord, SQLiteStore

_SETTINGS_KEY = "privata_vnext_settings"


class TtsError(RuntimeError):
    pass


class TtsUnavailableError(TtsError):
    pass


@dataclass(frozen=True)
class TtsSynthesisResult:
    output_path: Path
    model_name: str


class TtsClient(Protocol):
    def synthesize_to_wav(
        self,
        *,
        text: str,
        output_path: Path,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> TtsSynthesisResult: ...


class PiperTtsClient:
    def __init__(
        self,
        *,
        piper_bin: str | None = None,
        model_path: str | None = None,
    ) -> None:
        self._piper_bin = (
            piper_bin or os.getenv("TRANSCIBIO_PIPER_BIN") or shutil.which("piper") or ""
        )
        self._model_path = model_path or os.getenv("TRANSCIBIO_PIPER_MODEL") or ""

    def synthesize_to_wav(
        self,
        *,
        text: str,
        output_path: Path,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> TtsSynthesisResult:
        if not self._piper_bin:
            raise TtsUnavailableError("Piper binary not found in PATH (optional TTS dependency).")
        model = voice or self._model_path
        if not model:
            raise TtsUnavailableError(
                "Piper model is not configured. Set TRANSCIBIO_PIPER_MODEL or choose a voice in settings."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Piper uses length_scale (<1 faster, >1 slower). Map speed to inverse.
        length_scale = max(0.1, min(4.0, 1.0 / max(0.25, min(3.0, float(speed)))))
        command = [
            self._piper_bin,
            "--model",
            model,
            "--output_file",
            str(output_path),
            "--length_scale",
            str(length_scale),
        ]
        try:
            result = subprocess.run(
                command,
                input=text,
                text=True,
                capture_output=True,
                timeout=90,
                check=False,
            )
        except FileNotFoundError as exc:
            raise TtsUnavailableError("Piper binary not found (optional TTS dependency).") from exc
        except subprocess.TimeoutExpired as exc:
            raise TtsError("Piper TTS timed out while generating audio.") from exc
        if result.returncode != 0 or not output_path.exists():
            stderr = (result.stderr or "").strip()
            raise TtsError(stderr or "Piper TTS synthesis failed.")
        return TtsSynthesisResult(output_path=output_path, model_name=f"piper:{Path(model).name}")


class OptionalPiperTtsRunner:
    def __init__(self) -> None:
        self._client = PiperTtsClient()

    def synthesize_to_wav(
        self,
        *,
        text: str,
        output_path: Path,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> TtsSynthesisResult:
        return self._client.synthesize_to_wav(
            text=text, output_path=output_path, voice=voice, speed=speed
        )


@dataclass(frozen=True)
class TtsMessageStatus:
    message_id: str
    status: str
    audio_asset_id: str | None
    mime_type: str | None
    duration_ms: int | None
    error_message: str
    download_url: str | None
    model_name: str


class TtsOrchestrator:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        settings: AppSettings,
        tts_client: TtsClient | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._tts_client = tts_client or OptionalPiperTtsRunner()

    def generate_for_message(
        self,
        *,
        session_id: str,
        message_id: str,
        voice: str | None = None,
        speed: float | None = None,
        force_regenerate: bool = False,
    ) -> TtsMessageStatus:
        message = self._require_assistant_message(session_id=session_id, message_id=message_id)
        metadata = self._parse_metadata(message)
        if not force_regenerate and metadata.get("tts_status") == "succeeded":
            audio_asset_id = metadata.get("tts_audio_asset_id")
            if isinstance(audio_asset_id, str):
                asset = self._store.get_audio_asset(audio_asset_id)
                if asset is not None and asset.session_id == session_id:
                    return self._status_from_asset(
                        session_id=session_id, message_id=message_id, asset=asset, metadata=metadata
                    )

        payload_settings = self._store.get_app_setting(_SETTINGS_KEY) or {}
        tts_cfg = (
            payload_settings.get("tts") if isinstance(payload_settings.get("tts"), dict) else {}
        )
        effective_voice = voice if voice is not None else str((tts_cfg or {}).get("voice") or "")
        effective_speed_raw = speed if speed is not None else (tts_cfg or {}).get("speed", 1.0)
        try:
            effective_speed = float(effective_speed_raw)
        except (TypeError, ValueError):
            effective_speed = 1.0
        tts_dir = self._settings.sessions_root / session_id / "tts"
        output_path = tts_dir / f"message_{message_id}.wav"
        text = (message.content_plain_text or message.content_markdown or "").strip()
        if not text:
            status = self._update_tts_metadata(
                message, metadata, status="failed", error_message="Assistant message is empty."
            )
            return status

        try:
            synthesis = self._tts_client.synthesize_to_wav(
                text=text,
                output_path=output_path,
                voice=effective_voice or None,
                speed=effective_speed,
            )
        except TtsUnavailableError as exc:
            status = self._update_tts_metadata(
                message, metadata, status="failed", error_message=str(exc)
            )
            return status
        except TtsError as exc:
            status = self._update_tts_metadata(
                message, metadata, status="failed", error_message=str(exc)
            )
            return status

        duration_ms = self._probe_wav_duration_ms(output_path)
        rel_path = os.path.relpath(output_path, self._settings.data_root).replace("\\", "/")
        asset = self._store.create_audio_asset(
            session_id=session_id,
            kind="tts_response_audio",
            mime_type="audio/wav",
            file_path=rel_path,
            duration_ms=duration_ms,
            sample_rate_hz=None,
            channels=None,
        )
        metadata.update(
            {
                "tts_status": "succeeded",
                "tts_audio_asset_id": asset.id,
                "tts_error": "",
                "tts_model_name": synthesis.model_name,
            }
        )
        self._store.update_chat_message(message.id, metadata=metadata)
        return self._status_from_asset(
            session_id=session_id, message_id=message.id, asset=asset, metadata=metadata
        )

    def get_message_status(self, *, session_id: str, message_id: str) -> TtsMessageStatus:
        message = self._require_assistant_message(session_id=session_id, message_id=message_id)
        metadata = self._parse_metadata(message)
        audio_asset_id = metadata.get("tts_audio_asset_id")
        if isinstance(audio_asset_id, str):
            asset = self._store.get_audio_asset(audio_asset_id)
            if asset is not None and asset.session_id == session_id:
                return self._status_from_asset(
                    session_id=session_id, message_id=message_id, asset=asset, metadata=metadata
                )
        return TtsMessageStatus(
            message_id=message_id,
            status=str(metadata.get("tts_status") or "idle"),
            audio_asset_id=None,
            mime_type=None,
            duration_ms=None,
            error_message=str(metadata.get("tts_error") or ""),
            download_url=None,
            model_name=str(metadata.get("tts_model_name") or ""),
        )

    def get_audio_path(self, *, session_id: str, message_id: str) -> Path:
        status = self.get_message_status(session_id=session_id, message_id=message_id)
        if status.audio_asset_id is None:
            raise KeyError("tts_audio_not_found")
        asset = self._store.get_audio_asset(status.audio_asset_id)
        if asset is None or asset.session_id != session_id:
            raise KeyError("tts_audio_not_found")
        path = (self._settings.data_root / asset.file_path).resolve()
        if not path.exists():
            raise KeyError("tts_audio_not_found")
        return path

    def _require_assistant_message(self, *, session_id: str, message_id: str) -> ChatMessageRecord:
        message = self._store.get_chat_message(message_id)
        if message is None or message.session_id != session_id:
            raise KeyError("message_not_found")
        if message.role != "assistant":
            raise ValueError("TTS can only be generated for assistant messages.")
        return message

    @staticmethod
    def _parse_metadata(message: ChatMessageRecord) -> dict[str, Any]:
        try:
            metadata = json.loads(message.metadata_json or "{}")
        except Exception:
            metadata = {}
        return metadata if isinstance(metadata, dict) else {}

    def _status_from_asset(
        self,
        *,
        session_id: str,
        message_id: str,
        asset: AudioAssetRecord,
        metadata: dict[str, Any],
    ) -> TtsMessageStatus:
        return TtsMessageStatus(
            message_id=message_id,
            status="succeeded",
            audio_asset_id=asset.id,
            mime_type=asset.mime_type,
            duration_ms=asset.duration_ms,
            error_message="",
            download_url=f"/api/v1/sessions/{session_id}/tts/{message_id}/audio",
            model_name=str(metadata.get("tts_model_name") or ""),
        )

    def _update_tts_metadata(
        self,
        message: ChatMessageRecord,
        metadata: dict[str, Any],
        *,
        status: str,
        error_message: str,
    ) -> TtsMessageStatus:
        metadata = dict(metadata)
        metadata.update(
            {
                "tts_status": status,
                "tts_error": error_message,
                "tts_audio_asset_id": None,
            }
        )
        self._store.update_chat_message(message.id, metadata=metadata)
        return TtsMessageStatus(
            message_id=message.id,
            status=status,
            audio_asset_id=None,
            mime_type=None,
            duration_ms=None,
            error_message=error_message,
            download_url=None,
            model_name=str(metadata.get("tts_model_name") or ""),
        )

    @staticmethod
    def _probe_wav_duration_ms(path: Path) -> int:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate() or 1
        return int(round((frames / rate) * 1000))
