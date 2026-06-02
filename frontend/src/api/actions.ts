import { apiFetch, apiFetchJson, artifactDownloadUrl } from "./client";
import type {
  ActionMutationResponse,
  ChatActionProposal,
} from "@/types/chat";

export function listActions(
  sessionId: string,
  status?: string,
): Promise<ChatActionProposal[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiFetch<ChatActionProposal[]>(
    `/api/v1/sessions/${sessionId}/actions${qs}`,
  );
}

export function confirmAction(
  sessionId: string,
  actionId: string,
): Promise<ActionMutationResponse> {
  return apiFetchJson<ActionMutationResponse>(
    `/api/v1/sessions/${sessionId}/actions/${actionId}/confirm`,
    "POST",
  );
}

export function cancelAction(
  sessionId: string,
  actionId: string,
): Promise<ActionMutationResponse> {
  return apiFetchJson<ActionMutationResponse>(
    `/api/v1/sessions/${sessionId}/actions/${actionId}/cancel`,
    "POST",
  );
}

export function artifactUrl(sessionId: string, artifactId: string): string {
  return artifactDownloadUrl(sessionId, artifactId);
}
