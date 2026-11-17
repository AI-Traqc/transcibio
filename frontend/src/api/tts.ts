import { apiFetch, apiFetchJson, ttsAudioUrl } from "./client";
import type { TtsGenerateRequest, TtsStatusResponse } from "@/types/tts";

export function generateTts(
  sessionId: string,
  body: TtsGenerateRequest,
): Promise<TtsStatusResponse> {
  return apiFetchJson<TtsStatusResponse>(
    `/api/v1/sessions/${sessionId}/tts`,
    "POST",
    body,
  );
}

export function getTtsStatus(
  sessionId: string,
  messageId: string,
): Promise<TtsStatusResponse> {
  return apiFetch<TtsStatusResponse>(
    `/api/v1/sessions/${sessionId}/tts/${messageId}`,
  );
}

export function ttsAudio(sessionId: string, messageId: string): string {
  return ttsAudioUrl(sessionId, messageId);
}
