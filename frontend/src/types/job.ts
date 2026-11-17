export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "canceled";

export type JobResponse = {
  id: string;
  session_id: string | null;
  job_type: string;
  status: string;
  progress: number;
  created_at_utc: string;
  started_at_utc: string | null;
  finished_at_utc: string | null;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  error_message: string;
};

export type JobEventEnvelope = {
  type: string;
  job_id: string;
  timestamp: string;
  payload: Record<string, unknown>;
};

export type CreateTranscriptionJobRequest = {
  audio_asset_id: string;
  language_hint?: "auto" | "en" | "de";
  stt_preset?: "fast" | "balanced" | "quality";
  diarization_enabled?: boolean;
};

export type CreateTranscriptionJobResponse = {
  job_id: string;
  status: string;
};

export type TranscriptionUiEvent = {
  id: string;
  time: string;
  type: string;
  message: string;
};

export type JobUiState = {
  jobId: string;
  status: string;
  progress: number;
  events: TranscriptionUiEvent[];
  errorMessage: string;
  output: Record<string, unknown> | null;
  stage?: string;
  stageMessage?: string;
  startedAt?: number;
};

export const TERMINAL_JOB_STATUSES = new Set<string>([
  "succeeded",
  "failed",
  "canceled",
]);
