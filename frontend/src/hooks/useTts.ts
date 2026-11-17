import { useCallback, useEffect, useState } from "react";
import * as ttsApi from "@/api/tts";
import type { TtsGenerateRequest, TtsStatusResponse } from "@/types/tts";

export interface UseTtsResult {
  statuses: Record<string, TtsStatusResponse>;
  busyMessageId: string | null;
  error: string | null;
  generate: (
    body: TtsGenerateRequest,
  ) => Promise<TtsStatusResponse>;
  refresh: (messageId: string) => Promise<void>;
  audioUrl: (messageId: string) => string;
}

export function useTts(sessionId: string | null): UseTtsResult {
  const [statuses, setStatuses] = useState<Record<string, TtsStatusResponse>>({});
  const [busyMessageId, setBusyMessageId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const setStatus = useCallback((status: TtsStatusResponse) => {
    setStatuses((prev) => ({ ...prev, [status.message_id]: status }));
  }, []);

  const reset = useCallback(() => {
    setStatuses({});
    setBusyMessageId(null);
    setError(null);
  }, []);

  useEffect(() => {
    reset();
  }, [sessionId, reset]);

  const generate = useCallback(
    async (body: TtsGenerateRequest) => {
      if (!sessionId) throw new Error("No active session");
      setBusyMessageId(body.message_id);
      setError(null);
      try {
        const status = await ttsApi.generateTts(sessionId, body);
        setStatus(status);
        return status;
      } catch (err) {
        setError(err instanceof Error ? err.message : "TTS failed");
        throw err;
      } finally {
        setBusyMessageId(null);
      }
    },
    [sessionId, setStatus],
  );

  const refresh = useCallback(
    async (messageId: string) => {
      if (!sessionId) return;
      const status = await ttsApi.getTtsStatus(sessionId, messageId);
      setStatus(status);
    },
    [sessionId, setStatus],
  );

  const audioUrl = useCallback(
    (messageId: string) => {
      if (!sessionId) return "";
      return ttsApi.ttsAudio(sessionId, messageId);
    },
    [sessionId],
  );

  return { statuses, busyMessageId, error, generate, refresh, audioUrl };
}
