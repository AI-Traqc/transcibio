export type VoiceCommandSendMode = "review_then_send" | "auto_send";

export type VoiceCommandRecordingState =
  | "idle"
  | "requesting"
  | "recording"
  | "uploading";

export type VoiceCommandResponse = {
  voice_command_id: string;
  session_id: string;
  thread_id: string;
  audio_asset_id: string;
  send_mode: VoiceCommandSendMode;
  transcribed_text: string;
  edited_text: string;
  detected_language: string;
  stt_model: string;
  warning: string;
  // True when STT produced no usable text; `transcribed_text` is then a placeholder,
  // not a real utterance. The hands-free loop uses this to skip non-speech turns.
  transcription_empty: boolean;
  user_message_id: string | null;
  assistant_message_id: string | null;
  job_id: string | null;
};
