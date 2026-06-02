import { useCallback, useEffect, useRef, useState } from "react";
import type { RecordingState } from "@/types/session";

export type RecorderKind = "command" | "meeting";

export interface UseVoiceRecorderResult {
  state: RecordingState;
  elapsedMs: number;
  error: string | null;
  start: () => Promise<void>;
  stop: () => Promise<{ blob: Blob; mimeType: string; fileName: string } | null>;
  cancel: () => void;
}

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

function chooseMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  for (const mime of MIME_CANDIDATES) {
    try {
      if (MediaRecorder.isTypeSupported(mime)) return mime;
    } catch {
      // ignore
    }
  }
  return undefined;
}

function extensionFor(mime: string | undefined): string {
  if (!mime) return "webm";
  if (mime.includes("webm")) return "webm";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("mp4")) return "m4a";
  if (mime.includes("wav")) return "wav";
  return "webm";
}

export function useVoiceRecorder(
  kind: RecorderKind,
  resetKey?: string | null,
): UseVoiceRecorderResult {
  const [state, setState] = useState<RecordingState>("idle");
  const [elapsedMs, setElapsedMs] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const startedAtRef = useRef<number>(0);
  const tickerRef = useRef<number | null>(null);
  const stopResolveRef = useRef<
    ((value: { blob: Blob; mimeType: string; fileName: string } | null) => void)
    | null
  >(null);

  const cleanup = useCallback(() => {
    if (tickerRef.current !== null) {
      window.clearInterval(tickerRef.current);
      tickerRef.current = null;
    }
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }
    recorderRef.current = null;
    chunksRef.current = [];
    startedAtRef.current = 0;
    setElapsedMs(0);
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const start = useCallback(async () => {
    if (state !== "idle") return;
    if (typeof navigator === "undefined" || !navigator.mediaDevices) {
      setError("Microphone not available in this environment");
      return;
    }
    setState("requesting");
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = chooseMimeType();
      const recorder = new MediaRecorder(
        stream,
        mimeType ? { mimeType } : undefined,
      );
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        const mime = recorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: mime });
        const fileName = `${kind}-${Date.now()}.${extensionFor(mime)}`;
        const resolve = stopResolveRef.current;
        stopResolveRef.current = null;
        cleanup();
        setState("idle");
        if (resolve) resolve({ blob, mimeType: mime, fileName });
      };
      recorder.onerror = () => {
        const resolve = stopResolveRef.current;
        stopResolveRef.current = null;
        setError("Recording failed");
        cleanup();
        setState("idle");
        if (resolve) resolve(null);
      };

      recorder.start(250);
      setState("recording");
      startedAtRef.current = Date.now();
      tickerRef.current = window.setInterval(() => {
        setElapsedMs(Date.now() - startedAtRef.current);
      }, 200);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to access microphone");
      cleanup();
      setState("idle");
    }
  }, [state, kind, cleanup]);

  const stop = useCallback(async () => {
    if (state !== "recording") return null;
    const recorder = recorderRef.current;
    if (!recorder) return null;
    setState("uploading");
    return new Promise<{ blob: Blob; mimeType: string; fileName: string } | null>(
      (resolve) => {
        stopResolveRef.current = resolve;
        try {
          recorder.stop();
        } catch {
          cleanup();
          setState("idle");
          resolve(null);
        }
      },
    );
  }, [state, cleanup]);

  const cancel = useCallback(() => {
    const recorder = recorderRef.current;
    stopResolveRef.current = null;
    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.stop();
      } catch {
        // ignore
      }
    }
    cleanup();
    setState("idle");
  }, [cleanup]);

  useEffect(() => {
    const recorder = recorderRef.current;
    stopResolveRef.current = null;
    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.stop();
      } catch {
        // ignore
      }
    }
    cleanup();
    setState("idle");
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey]);

  return { state, elapsedMs, error, start, stop, cancel };
}
