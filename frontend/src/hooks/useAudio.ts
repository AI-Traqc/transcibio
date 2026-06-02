import { useCallback, useEffect, useState } from "react";
import * as sessionsApi from "@/api/sessions";
import type {
  AudioUploadResponse,
  RecordingState,
} from "@/types/session";
import type {
  CreateTranscriptionJobRequest,
  CreateTranscriptionJobResponse,
} from "@/types/job";

export interface UseAudioResult {
  audio: AudioUploadResponse | null;
  recordingState: RecordingState;
  setRecordingState: (state: RecordingState) => void;
  uploading: boolean;
  error: string | null;
  reset: () => void;
  uploadFile: (file: File) => Promise<AudioUploadResponse>;
  uploadRecording: (blob: Blob, fileName: string) => Promise<AudioUploadResponse>;
  startTranscription: (
    audioAssetId: string,
    options?: Partial<CreateTranscriptionJobRequest>,
  ) => Promise<CreateTranscriptionJobResponse>;
}

export function useAudio(sessionId: string | null): UseAudioResult {
  const [audio, setAudio] = useState<AudioUploadResponse | null>(null);
  const [recordingState, setRecordingState] = useState<RecordingState>("idle");
  const [uploading, setUploading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setAudio(null);
    setRecordingState("idle");
    setError(null);
  }, []);

  useEffect(() => {
    reset();
    if (!sessionId) return;
    sessionsApi.getSessionAudio(sessionId).then((result) => {
      if (result) setAudio(result);
    }).catch(() => {});
  }, [sessionId, reset]);

  const uploadFile = useCallback(
    async (file: File) => {
      if (!sessionId) throw new Error("No active session");
      setUploading(true);
      setError(null);
      try {
        const result = await sessionsApi.uploadAudio(sessionId, file);
        setAudio(result);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Upload failed";
        setError(message);
        throw err;
      } finally {
        setUploading(false);
      }
    },
    [sessionId],
  );

  const uploadRecording = useCallback(
    async (blob: Blob, fileName: string) => {
      if (!sessionId) throw new Error("No active session");
      setUploading(true);
      setError(null);
      try {
        const result = await sessionsApi.uploadRecording(sessionId, blob, fileName);
        setAudio(result);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Upload failed";
        setError(message);
        throw err;
      } finally {
        setUploading(false);
      }
    },
    [sessionId],
  );

  const startTranscription = useCallback(
    async (
      audioAssetId: string,
      options: Partial<CreateTranscriptionJobRequest> = {},
    ) => {
      if (!sessionId) throw new Error("No active session");
      return sessionsApi.createTranscriptionJob(sessionId, {
        audio_asset_id: audioAssetId,
        language_hint: options.language_hint ?? "auto",
        stt_preset: options.stt_preset ?? "balanced",
        diarization_enabled: options.diarization_enabled ?? true,
      });
    },
    [sessionId],
  );

  return {
    audio,
    recordingState,
    setRecordingState,
    uploading,
    error,
    reset,
    uploadFile,
    uploadRecording,
    startTranscription,
  };
}
