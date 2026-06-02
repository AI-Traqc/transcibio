from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.api.deps import get_app_settings, get_model_discovery, get_store
from backend.app.config import AppSettings
from backend.app.services.local_llm import normalize_backend_llm_provider, resolve_local_llm_config
from backend.app.services.model_discovery import ModelDiscoveryService
from backend.app.store import SQLiteStore

router = APIRouter(prefix="/settings", tags=["settings"])

_SETTINGS_KEY = "privata_vnext_settings"

ProfileName = Literal["fast", "balanced", "quality"]
LanguageHint = Literal["auto", "en", "de"]
VoiceSendMode = Literal["review_then_send", "auto_send"]
ChatProvider = Literal["ollama"]
ResponseDetail = Literal["brief", "normal", "detailed"]
TtsProvider = Literal["piper"]
VoiceEngine = Literal["piper", "kokoro"]


class SttSettingsResponse(BaseModel):
    default_language_hint: LanguageHint = "auto"
    default_preset: ProfileName = "balanced"
    diarization_enabled_default: bool = True
    model: str = ""


class ChatSettingsResponse(BaseModel):
    llm_provider: ChatProvider = "ollama"
    model_name: str = ""
    response_detail: ResponseDetail = "normal"


class VoiceCommandSettingsResponse(BaseModel):
    default_send_mode: VoiceSendMode = "review_then_send"


class TtsSettingsResponse(BaseModel):
    enabled: bool = False
    auto_generate_on_chat_reply: bool = False
    auto_play: bool = False
    provider: TtsProvider = "piper"
    voice: str = ""
    speed: float = Field(default=1.0, ge=0.25, le=3.0)
    # Streaming voice-mode engine: piper (German) or kokoro (English).
    voice_engine: VoiceEngine = "piper"


class UiSettingsResponse(BaseModel):
    show_timestamps_in_citations: bool = True


class SettingsResponse(BaseModel):
    processing_profile: ProfileName = "balanced"
    stt: SttSettingsResponse = Field(default_factory=SttSettingsResponse)
    chat: ChatSettingsResponse = Field(default_factory=ChatSettingsResponse)
    voice_commands: VoiceCommandSettingsResponse = Field(
        default_factory=VoiceCommandSettingsResponse
    )
    tts: TtsSettingsResponse = Field(default_factory=TtsSettingsResponse)
    ui: UiSettingsResponse = Field(default_factory=UiSettingsResponse)


class SttSettingsPatch(BaseModel):
    default_language_hint: LanguageHint | None = None
    default_preset: ProfileName | None = None
    diarization_enabled_default: bool | None = None
    model: str | None = None


class ChatSettingsPatch(BaseModel):
    # Accepts any value (incl. legacy "none"/"lmstudio"); the handler normalizes it
    # via `normalize_backend_llm_provider`, which always resolves to "ollama". The
    # GET/response model stays strict (`ChatProvider`).
    llm_provider: str | None = None
    model_name: str | None = None
    response_detail: ResponseDetail | None = None


class VoiceCommandSettingsPatch(BaseModel):
    default_send_mode: VoiceSendMode | None = None


class TtsSettingsPatch(BaseModel):
    enabled: bool | None = None
    auto_generate_on_chat_reply: bool | None = None
    auto_play: bool | None = None
    provider: TtsProvider | None = None
    voice: str | None = None
    speed: float | None = Field(default=None, ge=0.25, le=3.0)
    voice_engine: VoiceEngine | None = None


class UiSettingsPatch(BaseModel):
    show_timestamps_in_citations: bool | None = None


class SettingsPatchRequest(BaseModel):
    processing_profile: ProfileName | None = None
    stt: SttSettingsPatch | None = None
    chat: ChatSettingsPatch | None = None
    voice_commands: VoiceCommandSettingsPatch | None = None
    tts: TtsSettingsPatch | None = None
    ui: UiSettingsPatch | None = None


def _defaults_from_app_settings(app_settings: AppSettings) -> dict[str, Any]:
    llm_provider = normalize_backend_llm_provider(app_settings.llm_provider)
    tts_provider = (app_settings.tts_provider or "piper").strip().lower()
    if tts_provider != "piper":
        tts_provider = "piper"
    profile = (
        app_settings.processing_profile
        if app_settings.processing_profile in {"fast", "balanced", "quality"}
        else "balanced"
    )
    return {
        "processing_profile": profile,
        "stt": {
            "default_language_hint": "auto",
            "default_preset": profile,
            "diarization_enabled_default": True,
        },
        "chat": {
            "llm_provider": llm_provider,
            "model_name": "",
            "response_detail": "normal",
        },
        "voice_commands": {
            "default_send_mode": "review_then_send",
        },
        "tts": {
            "enabled": False,
            "auto_generate_on_chat_reply": False,
            "auto_play": False,
            "provider": tts_provider,
            "voice": "",
            "speed": 1.0,
        },
        "ui": {
            "show_timestamps_in_citations": True,
        },
    }


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_effective_settings(store: SQLiteStore, app_settings: AppSettings) -> SettingsResponse:
    defaults = _defaults_from_app_settings(app_settings)
    persisted = store.get_app_setting(_SETTINGS_KEY) or {}
    merged = _deep_merge(defaults, persisted)
    chat_settings = merged.get("chat")
    if isinstance(chat_settings, dict):
        chat_settings["llm_provider"] = normalize_backend_llm_provider(
            chat_settings.get("llm_provider")
        )
    return SettingsResponse.model_validate(merged)


@router.get("", response_model=SettingsResponse)
def get_settings(
    store: Annotated[SQLiteStore, Depends(get_store)],
    app_settings: Annotated[AppSettings, Depends(get_app_settings)],
) -> SettingsResponse:
    return _load_effective_settings(store, app_settings)


@router.patch("", response_model=SettingsResponse)
def patch_settings(
    payload: SettingsPatchRequest,
    store: Annotated[SQLiteStore, Depends(get_store)],
    app_settings: Annotated[AppSettings, Depends(get_app_settings)],
) -> SettingsResponse:
    current = _load_effective_settings(store, app_settings)
    patch_dict = payload.model_dump(exclude_none=True)
    if not patch_dict:
        return current
    chat_patch = patch_dict.get("chat")
    if isinstance(chat_patch, dict):
        chat_patch["llm_provider"] = normalize_backend_llm_provider(chat_patch.get("llm_provider"))
    merged = _deep_merge(current.model_dump(), patch_dict)
    validated = SettingsResponse.model_validate(merged)
    store.set_app_setting(_SETTINGS_KEY, validated.model_dump())
    return validated


class ProviderModelsResponse(BaseModel):
    provider: str
    current: str
    available: list[str]
    reachable: bool
    error: str = ""


class ModelsResponse(BaseModel):
    stt: ProviderModelsResponse
    llm: ProviderModelsResponse
    diarization: ProviderModelsResponse


@router.get("/models", response_model=ModelsResponse)
def get_available_models(
    store: Annotated[SQLiteStore, Depends(get_store)],
    app_settings: Annotated[AppSettings, Depends(get_app_settings)],
    discovery: Annotated[ModelDiscoveryService, Depends(get_model_discovery)],
) -> ModelsResponse:
    effective = _load_effective_settings(store, app_settings)
    llm_config = resolve_local_llm_config(store=store, settings=app_settings)

    stt_current = effective.stt.model or effective.stt.default_preset
    stt = discovery.get_stt_models(current_model=stt_current)
    llm = discovery.get_llm_models(current_model=llm_config.model_name)
    diarization = discovery.get_diarization_info(enabled=effective.stt.diarization_enabled_default)

    return ModelsResponse(
        stt=ProviderModelsResponse(**vars(stt)),
        llm=ProviderModelsResponse(**vars(llm)),
        diarization=ProviderModelsResponse(**vars(diarization)),
    )
