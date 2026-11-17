import { useCallback, useEffect, useState } from "react";
import * as transcriptsApi from "@/api/transcripts";
import type {
  CreateCorrectionProposalRequest,
  TranscriptResponse,
  TranscriptRevisionSummary,
} from "@/types/transcript";

export interface UseTranscriptResult {
  transcript: TranscriptResponse | null;
  revisions: TranscriptRevisionSummary[];
  loading: boolean;
  error: string | null;
  load: (revisionId?: string) => Promise<void>;
  reset: () => void;
  patchSegment: (segmentId: string, text: string) => Promise<void>;
  patchSpeaker: (speakerId: string, displayName: string) => Promise<void>;
  createCorrection: (
    body: CreateCorrectionProposalRequest,
  ) => ReturnType<typeof transcriptsApi.createCorrectionProposal>;
  applyCorrection: (
    proposalId: string,
  ) => ReturnType<typeof transcriptsApi.applyCorrectionProposal>;
}

export function useTranscript(sessionId: string | null): UseTranscriptResult {
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [revisions, setRevisions] = useState<TranscriptRevisionSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setTranscript(null);
    setRevisions([]);
    setError(null);
  }, []);

  useEffect(() => {
    reset();
  }, [sessionId, reset]);

  const load = useCallback(
    async (revisionId?: string) => {
      if (!sessionId) return;
      setLoading(true);
      setError(null);
      try {
        const [t, revs] = await Promise.all([
          transcriptsApi.getTranscript(sessionId, revisionId),
          transcriptsApi.listRevisions(sessionId),
        ]);
        setTranscript(t);
        setRevisions(revs);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load transcript");
      } finally {
        setLoading(false);
      }
    },
    [sessionId],
  );

  const patchSegment = useCallback(
    async (segmentId: string, text: string) => {
      if (!sessionId) return;
      const updated = await transcriptsApi.patchSegment(sessionId, segmentId, text);
      setTranscript(updated);
      const revs = await transcriptsApi.listRevisions(sessionId);
      setRevisions(revs);
    },
    [sessionId],
  );

  const patchSpeaker = useCallback(
    async (speakerId: string, displayName: string) => {
      if (!sessionId) return;
      const updated = await transcriptsApi.patchSpeaker(
        sessionId,
        speakerId,
        displayName,
      );
      setTranscript(updated);
      const revs = await transcriptsApi.listRevisions(sessionId);
      setRevisions(revs);
    },
    [sessionId],
  );

  const createCorrection = useCallback(
    (body: CreateCorrectionProposalRequest) => {
      if (!sessionId) throw new Error("No active session");
      return transcriptsApi.createCorrectionProposal(sessionId, body);
    },
    [sessionId],
  );

  const applyCorrection = useCallback(
    async (proposalId: string) => {
      if (!sessionId) throw new Error("No active session");
      const result = await transcriptsApi.applyCorrectionProposal(
        sessionId,
        proposalId,
      );
      setTranscript(result.transcript);
      const revs = await transcriptsApi.listRevisions(sessionId);
      setRevisions(revs);
      return result;
    },
    [sessionId],
  );

  return {
    transcript,
    revisions,
    loading,
    error,
    load,
    reset,
    patchSegment,
    patchSpeaker,
    createCorrection,
    applyCorrection,
  };
}
