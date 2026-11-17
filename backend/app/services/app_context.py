"""Short self-description of Transcibio for the chat model, built from the live settings.

Without it the model knows nothing about the app it runs in, so "How does this work?" or
"Which models do you use?" got generic answers about AI. The text names the components
that are actually configured right now, so it stays correct when settings change.
"""

from __future__ import annotations

from backend.app.config import AppSettings
from backend.app.services.local_llm import resolve_local_llm_config
from backend.app.services.stt import FasterWhisperSttClient
from backend.app.services.transcription_orchestrator import (
    NEMOTRON_ENGINE,
    resolve_stt_job_defaults,
)
from backend.app.store import SQLiteStore

_SETTINGS_KEY = "privata_vnext_settings"
_NEMOTRON = "NVIDIA Nemotron 3.5 Transcribe"
_VOICES = {
    "piper": {"de": "Piper (deutsche Stimme Thorsten)", "en": "Piper (German voice Thorsten)"},
    "kokoro": {"de": "Kokoro (englische Stimme)", "en": "Kokoro (English voice)"},
}


def _stored_voice_engine(store: SQLiteStore) -> str:
    persisted = store.get_app_setting(_SETTINGS_KEY) or {}
    tts = persisted.get("tts") if isinstance(persisted, dict) else None
    engine = tts.get("voice_engine") if isinstance(tts, dict) else None
    return engine if engine in _VOICES else "piper"


def build_app_context(
    store: SQLiteStore,
    settings: AppSettings,
    *,
    language: str,
    voice_engine: str | None = None,
) -> str:
    """Describe the app and its current models in `language` ("de" or anything else = en)."""
    stt = resolve_stt_job_defaults(store, default_preset=settings.processing_profile)
    llm = resolve_local_llm_config(store=store, settings=settings)
    whisper = FasterWhisperSttClient()
    meeting_model = whisper.meeting_model_map[stt.preset]
    command_model = whisper.command_model_map[stt.preset]
    voice = _VOICES[voice_engine if voice_engine in _VOICES else _stored_voice_engine(store)]
    de = language == "de"
    lang = "de" if de else "en"

    if stt.engine == NEMOTRON_ENGINE:
        transcription = (
            f"{_NEMOTRON} (Text und Sprecher in einem Modell)"
            if de
            else f"{_NEMOTRON} (text and speakers in one model)"
        )
        voice_input = _NEMOTRON
    else:
        transcription = (
            f"Whisper (faster-whisper „{meeting_model}“) mit Sprechererkennung durch pyannote"
            if de
            else f'Whisper (faster-whisper "{meeting_model}") with pyannote speaker detection'
        )
        voice_input = (
            f"Whisper (faster-whisper „{command_model}“)"
            if de
            else (f'Whisper (faster-whisper "{command_model}")')
        )
    if de:
        thinking = "an" if llm.think else "aus"
        speakers = "an" if stt.diarization_enabled else "aus"
        return (
            "Über Transcibio (nutze das, wenn nach der App, ihrer Funktionsweise oder ihren "
            "Modellen gefragt wird; das ist kein Transkript, also ohne Quellenangaben): Transcibio ist ein lokaler Assistent, der komplett auf "
            "diesem Gerät läuft; nichts wird ins Internet gesendet. Er transkribiert "
            "Aufnahmen und hochgeladene Audiodateien, erkennt, wer spricht, beantwortet "
            "Fragen zum Transkript im Chat und im Sprachmodus und schlägt Aktionen wie "
            f"E-Mail-Entwürfe vor. Aktuell: Transkription mit {transcription} "
            f"(Sprechererkennung {speakers}); Spracheingabe mit {voice_input}; Antworten "
            f"von {llm.model_name} über Ollama (Denkmodus {thinking}, nur im Text-Chat); "
            f"Sprachausgabe mit {voice[lang]}. Alles lässt sich in den Einstellungen ändern."
        )
    thinking = "on" if llm.think else "off"
    speakers = "on" if stt.diarization_enabled else "off"
    return (
        "About Transcibio (use this when asked about the app, how it works or its models; "
        "it is not a transcript, so give no source markers): "
        "Transcibio is a local assistant that runs entirely on this device; nothing is sent "
        "to the internet. It transcribes recordings and uploaded audio, detects who is "
        "speaking, answers questions about the transcript in chat and voice mode, and "
        f"suggests actions such as email drafts. Currently: transcription with {transcription} "
        f"(speaker detection {speakers}); voice input with {voice_input}; answers from "
        f"{llm.model_name} via Ollama (thinking mode {thinking}, typed chat only); voice "
        f"output with {voice[lang]}. All of this can be changed in Settings."
    )
