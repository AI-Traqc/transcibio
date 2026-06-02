import { apiFetch, apiFetchEmpty, apiFetchJson, apiForm } from "./client";
import type {
  AudioUploadResponse,
  CreateSessionRequest,
  SessionRecord,
  UpdateSessionRequest,
} from "@/types/session";
import type {
  CreateTranscriptionJobRequest,
  CreateTranscriptionJobResponse,
} from "@/types/job";

export function listSessions(params: {
  q?: string;
  limit?: number;
} = {}): Promise<SessionRecord[]> {
  const searchParams = new URLSearchParams();
  if (params.q) searchParams.set("q", params.q);
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  return apiFetch<SessionRecord[]>(
    `/api/v1/sessions${qs ? `?${qs}` : ""}`,
  );
}

export function getSession(sessionId: string): Promise<SessionRecord> {
  return apiFetch<SessionRecord>(`/api/v1/sessions/${sessionId}`);
}

export function createSession(
  body: CreateSessionRequest,
): Promise<SessionRecord> {
  return apiFetchJson<SessionRecord>("/api/v1/sessions", "POST", body);
}

export function renameSession(
  sessionId: string,
  body: UpdateSessionRequest,
): Promise<SessionRecord> {
  return apiFetchJson<SessionRecord>(
    `/api/v1/sessions/${sessionId}`,
    "PATCH",
    body,
  );
}

export function deleteSession(sessionId: string): Promise<void> {
  return apiFetchEmpty(`/api/v1/sessions/${sessionId}`, "DELETE");
}

export function deleteAllSessions(): Promise<{ deleted_count: number }> {
  return apiFetchJson<{ deleted_count: number }>(
    "/api/v1/sessions",
    "DELETE",
  );
}

export function getSessionAudio(
  sessionId: string,
): Promise<AudioUploadResponse | null> {
  return apiFetch<AudioUploadResponse | null>(
    `/api/v1/sessions/${sessionId}/audio`,
  );
}

export function uploadAudio(
  sessionId: string,
  file: File,
): Promise<AudioUploadResponse> {
  const form = new FormData();
  form.append("audio_file", file);
  return apiForm<AudioUploadResponse>(
    `/api/v1/sessions/${sessionId}/audio/upload`,
    form,
  );
}

export function uploadRecording(
  sessionId: string,
  blob: Blob,
  fileName: string,
): Promise<AudioUploadResponse> {
  const form = new FormData();
  form.append("audio_file", blob, fileName);
  return apiForm<AudioUploadResponse>(
    `/api/v1/sessions/${sessionId}/audio/recording`,
    form,
  );
}

export function createTranscriptionJob(
  sessionId: string,
  body: CreateTranscriptionJobRequest,
): Promise<CreateTranscriptionJobResponse> {
  return apiFetchJson<CreateTranscriptionJobResponse>(
    `/api/v1/sessions/${sessionId}/transcription-jobs`,
    "POST",
    body,
  );
}
