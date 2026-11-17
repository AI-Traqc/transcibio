import { apiFetch, apiFetchJson } from "./client";
import type {
  ChatMessage,
  CreateChatMessageRequest,
  CreateChatMessageResponse,
  SessionChatResponse,
} from "@/types/chat";

export function getSessionChat(
  sessionId: string,
): Promise<SessionChatResponse> {
  return apiFetch<SessionChatResponse>(
    `/api/v1/sessions/${sessionId}/chat`,
  );
}

export function getChatMessage(
  sessionId: string,
  messageId: string,
): Promise<ChatMessage> {
  return apiFetch<ChatMessage>(
    `/api/v1/sessions/${sessionId}/chat/messages/${messageId}`,
  );
}

export function sendChatMessage(
  sessionId: string,
  body: CreateChatMessageRequest,
): Promise<CreateChatMessageResponse> {
  return apiFetchJson<CreateChatMessageResponse>(
    `/api/v1/sessions/${sessionId}/chat/messages`,
    "POST",
    body,
  );
}
