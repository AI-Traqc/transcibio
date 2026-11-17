import { apiFetch, apiFetchJson } from "./client";
import type {
  ApplyTranscriptCorrectionResponse,
  CreateCorrectionProposalRequest,
  TranscriptCorrectionProposalResponse,
  TranscriptResponse,
  TranscriptRevisionSummary,
} from "@/types/transcript";

export function getTranscript(
  sessionId: string,
  revisionId?: string,
): Promise<TranscriptResponse> {
  const qs = revisionId
    ? `?revision_id=${encodeURIComponent(revisionId)}`
    : "";
  return apiFetch<TranscriptResponse>(
    `/api/v1/sessions/${sessionId}/transcript${qs}`,
  );
}

export function listRevisions(
  sessionId: string,
): Promise<TranscriptRevisionSummary[]> {
  return apiFetch<TranscriptRevisionSummary[]>(
    `/api/v1/sessions/${sessionId}/transcript/revisions`,
  );
}

export function patchSegment(
  sessionId: string,
  segmentId: string,
  text: string,
): Promise<TranscriptResponse> {
  return apiFetchJson<TranscriptResponse>(
    `/api/v1/sessions/${sessionId}/transcript/segments/${segmentId}`,
    "PATCH",
    { text },
  );
}

export function patchSpeaker(
  sessionId: string,
  speakerId: string,
  displayName: string,
): Promise<TranscriptResponse> {
  return apiFetchJson<TranscriptResponse>(
    `/api/v1/sessions/${sessionId}/transcript/speakers/${speakerId}`,
    "PATCH",
    { display_name: displayName },
  );
}

export function createCorrectionProposal(
  sessionId: string,
  body: CreateCorrectionProposalRequest,
): Promise<TranscriptCorrectionProposalResponse> {
  return apiFetchJson<TranscriptCorrectionProposalResponse>(
    `/api/v1/sessions/${sessionId}/transcript/correction-proposals`,
    "POST",
    body,
  );
}

export function getCorrectionProposal(
  sessionId: string,
  proposalId: string,
): Promise<TranscriptCorrectionProposalResponse> {
  return apiFetch<TranscriptCorrectionProposalResponse>(
    `/api/v1/sessions/${sessionId}/transcript/correction-proposals/${proposalId}`,
  );
}

export function applyCorrectionProposal(
  sessionId: string,
  proposalId: string,
): Promise<ApplyTranscriptCorrectionResponse> {
  return apiFetchJson<ApplyTranscriptCorrectionResponse>(
    `/api/v1/sessions/${sessionId}/transcript/correction-proposals/${proposalId}/apply`,
    "POST",
  );
}
