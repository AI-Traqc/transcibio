export type TtsStatusResponse = {
  message_id: string;
  status: string;
  audio_asset_id: string | null;
  mime_type: string | null;
  duration_ms: number | null;
  error_message: string;
  download_url: string | null;
  model_name: string;
};

export type TtsGenerateRequest = {
  message_id: string;
  voice?: string | null;
  speed?: number | null;
  force_regenerate?: boolean;
};
