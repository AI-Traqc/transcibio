import { useCallback, useEffect, useRef } from "react";
import { connectJobEvents, type JobEventStream } from "@/api/client";
import type { JobEventEnvelope } from "@/types/job";

export type JobEventKind = "transcription" | "chat" | "other";

export type JobEventHandlers = {
  onProgress?: (event: JobEventEnvelope) => void;
  onStage?: (event: JobEventEnvelope) => void;
  onSucceeded?: (event: JobEventEnvelope) => void;
  onFailed?: (event: JobEventEnvelope) => void;
  onEvent?: (event: JobEventEnvelope) => void;
};

type Subscription = {
  jobId: string;
  kind: JobEventKind;
  sessionId: string | null;
  stream: JobEventStream;
};

export interface UseJobEventsResult {
  attach: (
    jobId: string,
    kind: JobEventKind,
    handlers: JobEventHandlers,
    sessionId?: string | null,
  ) => void;
  detach: (jobId: string) => void;
  detachForSession: (sessionId: string) => void;
  detachAll: () => void;
}

export function useJobEvents(): UseJobEventsResult {
  const subsRef = useRef<Map<string, Subscription>>(new Map());

  const detach = useCallback((jobId: string) => {
    const existing = subsRef.current.get(jobId);
    if (existing) {
      existing.stream.close();
      subsRef.current.delete(jobId);
    }
  }, []);

  const detachForSession = useCallback((sessionId: string) => {
    for (const [jobId, sub] of subsRef.current.entries()) {
      if (sub.sessionId === sessionId) {
        sub.stream.close();
        subsRef.current.delete(jobId);
      }
    }
  }, []);

  const detachAll = useCallback(() => {
    for (const sub of subsRef.current.values()) {
      sub.stream.close();
    }
    subsRef.current.clear();
  }, []);

  const attach = useCallback(
    (
      jobId: string,
      kind: JobEventKind,
      handlers: JobEventHandlers,
      sessionId: string | null = null,
    ) => {
      const existing = subsRef.current.get(jobId);
      if (existing) {
        existing.stream.close();
        subsRef.current.delete(jobId);
      }

      // Guard against double-firing of terminal handlers: a late-attaching
      // client gets snapshot + synthetic terminal, while an early-attaching
      // client gets intermediate events + real terminal. If the server sends
      // both (or the browser auto-reconnects), we only want the first.
      let terminated = false;
      const stream = connectJobEvents(jobId, {
        onSnapshot: (e) => {
          if (terminated) return;
          handlers.onEvent?.(e);
        },
        onProgress: (e) => {
          if (terminated) return;
          handlers.onProgress?.(e);
          handlers.onEvent?.(e);
        },
        onStage: (e) => {
          if (terminated) return;
          handlers.onStage?.(e);
          handlers.onEvent?.(e);
        },
        onSucceeded: (e) => {
          if (terminated) return;
          terminated = true;
          handlers.onSucceeded?.(e);
          handlers.onEvent?.(e);
          const sub = subsRef.current.get(jobId);
          if (sub) {
            sub.stream.close();
            subsRef.current.delete(jobId);
          }
        },
        onFailed: (e) => {
          if (terminated) return;
          terminated = true;
          handlers.onFailed?.(e);
          handlers.onEvent?.(e);
          const sub = subsRef.current.get(jobId);
          if (sub) {
            sub.stream.close();
            subsRef.current.delete(jobId);
          }
        },
      });

      subsRef.current.set(jobId, { jobId, kind, sessionId, stream });
    },
    [],
  );

  useEffect(() => {
    return () => {
      detachAll();
    };
  }, [detachAll]);

  return { attach, detach, detachForSession, detachAll };
}
