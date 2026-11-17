export type SessionRecord = {
  id: string;
  created_at_utc: string;
  updated_at_utc: string;
  title: string;
  source_kind: string;
  source_name: string;
  source_language_hint: string;
  command_language_hint: string;
  status: string;
  last_error: string;
  active_transcript_revision_id: string | null;
};

export type AudioUploadResponse = {
  audio_asset_id: string;
  session_id: string;
  kind: string;
  file_name: string;
  file_path: string;
  mime_type: string;
  duration_ms: number;
  sample_rate_hz: number | null;
  channels: number | null;
};

export type CreateSessionRequest = {
  title: string;
  source_kind?: "upload" | "recording";
  source_name?: string;
  source_language_hint?: "auto" | "en" | "de";
  command_language_hint?: "auto" | "en" | "de";
};

export type UpdateSessionRequest = {
  title: string;
};

export type RecordingState = "idle" | "requesting" | "recording" | "uploading";
