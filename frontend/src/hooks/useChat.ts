import { useCallback, useEffect, useState } from "react";
import * as chatApi from "@/api/chat";
import type {
  ChatMessage,
  ChatThread,
  CreateChatMessageRequest,
  SessionChatResponse,
} from "@/types/chat";

export interface UseChatResult {
  thread: ChatThread | null;
  messages: ChatMessage[];
  pendingJobId: string | null;
  loading: boolean;
  error: string | null;
  setDraftFromVoice: (text: string) => void;
  draft: string;
  setDraft: (value: string) => void;
  reload: () => Promise<void>;
  send: (
    body: CreateChatMessageRequest,
  ) => Promise<{ userMessageId: string; assistantMessageId: string; jobId: string }>;
  reset: () => void;
}

export function useChat(sessionId: string | null): UseChatResult {
  const [thread, setThread] = useState<ChatThread | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingJobId, setPendingJobId] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>("");

  const reset = useCallback(() => {
    setThread(null);
    setMessages([]);
    setError(null);
    setPendingJobId(null);
    setDraft("");
  }, []);

  useEffect(() => {
    reset();
  }, [sessionId, reset]);

  const applyResponse = useCallback((data: SessionChatResponse) => {
    setThread(data.thread);
    setMessages(data.messages);
  }, []);

  const reload = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await chatApi.getSessionChat(sessionId);
      applyResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load chat");
    } finally {
      setLoading(false);
    }
  }, [sessionId, applyResponse]);

  const send = useCallback(
    async (body: CreateChatMessageRequest) => {
      if (!sessionId) throw new Error("No active session");
      const result = await chatApi.sendChatMessage(sessionId, body);
      setPendingJobId(result.job_id);
      const data = await chatApi.getSessionChat(sessionId);
      applyResponse(data);
      return {
        userMessageId: result.user_message_id,
        assistantMessageId: result.assistant_message_id,
        jobId: result.job_id,
      };
    },
    [sessionId, applyResponse],
  );

  const setDraftFromVoice = useCallback((text: string) => {
    setDraft(text);
  }, []);

  return {
    thread,
    messages,
    pendingJobId,
    loading,
    error,
    draft,
    setDraft,
    setDraftFromVoice,
    reload,
    send,
    reset,
  };
}
