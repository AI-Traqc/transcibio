import type { VoiceCommandSendMode } from "./voice";

export type ProcessingProfile = "fast" | "balanced" | "quality";
export type ResponseDetail = "brief" | "normal" | "detailed";
export type LanguageHint = "auto" | "en" | "de";
export type VoiceEngine = "piper" | "kokoro";
// Meeting transcription engine; voice commands always use faster-whisper.
export type SttEngine = "whisper-pyannote" | "nemotron";

export type SettingsPayload = {
  processing_profile: ProcessingProfile;
  stt: {
    default_language_hint: LanguageHint;
    default_preset: ProcessingProfile;
    diarization_enabled_default: boolean;
    engine: SttEngine;
  };
  chat: {
    llm_provider: "ollama";
    model_name: string;
    response_detail: ResponseDetail;
    // Thinking before answering (typed chat + transcript corrections; voice never thinks).
    think: boolean;
  };
  voice_commands: {
    default_send_mode: VoiceCommandSendMode;
  };
  tts: {
    enabled: boolean;
    auto_generate_on_chat_reply: boolean;
    auto_play: boolean;
    provider: "piper";
    voice: string;
    speed: number;
    voice_engine: VoiceEngine;
  };
  ui: {
    show_timestamps_in_citations: boolean;
  };
};

export type SettingsPatchRequest = Partial<{
  processing_profile: ProcessingProfile;
  stt: Partial<SettingsPayload["stt"]> & { model?: string };
  chat: Partial<SettingsPayload["chat"]>;
  voice_commands: Partial<SettingsPayload["voice_commands"]>;
  tts: Partial<SettingsPayload["tts"]>;
  ui: Partial<SettingsPayload["ui"]>;
}>;

export type ProviderModels = {
  provider: string;
  current: string;
  available: string[];
  reachable: boolean;
  error: string;
};

// "starting": the server process runs but doesn't answer yet (loading, warming up).
export type NemotronServerState = "running" | "starting" | "stopped";

export type NemotronStatus = ProviderModels & {
  state: NemotronServerState;
  starting_seconds?: number | null;
};

export type ModelsResponse = {
  stt: ProviderModels;
  llm: ProviderModels;
  diarization: ProviderModels;
  // Optional second transcription engine (Nemotron 3.5 Transcribe server).
  nemotron?: NemotronStatus;
  // Thinking support per installed chat model.
  llm_thinking?: Record<string, ThinkingSupport>;
};

// "optional": can be switched; "always": thinks even when off (gpt-oss); "none": can't think.
export type ThinkingSupport = "optional" | "always" | "none";
