import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ChatMessage } from "@/types/chat";
import type { JobUiState } from "@/types/job";
import type { SettingsPayload } from "@/types/settings";
import type { TranscriptResponse } from "@/types/transcript";
import type { TtsStatusResponse } from "@/types/tts";
import { EmptyState } from "./EmptyState";
import { JobProgressInline } from "./JobProgressInline";
import { MessageBubble } from "./MessageBubble";
import { TranscriptBlock } from "./TranscriptBlock";

interface ChatThreadProps {
  sessionId: string;
  messages: ChatMessage[];
  transcript: TranscriptResponse | null;
  transcriptionJob: JobUiState | null;
  chatJob: JobUiState | null;
  settings: SettingsPayload | null;
  ttsStatuses: Record<string, TtsStatusResponse>;
  ttsBusyMessageId: string | null;
  actionBusy: boolean;
  onQuickAction: (prompt: string) => void;
  onEditTranscript: () => void;
  onConfirmAction: (actionId: string) => void;
  onCancelAction: (actionId: string) => void;
  onGenerateTts: (messageId: string) => void;
  getTtsAudioUrl: (messageId: string) => string;
  audioSrc: string | null;
  audioDurationMs: number;
}

export function ChatThread({
  sessionId,
  messages,
  transcript,
  transcriptionJob,
  chatJob,
  settings,
  ttsStatuses,
  ttsBusyMessageId,
  actionBusy,
  onQuickAction,
  onEditTranscript,
  onConfirmAction,
  onCancelAction,
  onGenerateTts,
  getTtsAudioUrl,
  audioSrc,
  audioDurationMs,
}: ChatThreadProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
  }, [messages.length, transcript?.revision.id]);

  const hasContent =
    messages.length > 0 || transcript !== null || transcriptionJob !== null;

  if (!hasContent) {
    return <EmptyState variant="no-audio" />;
  }

  return (
    <ScrollArea className="h-full scrollbar-thin">
      <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col">
        {transcript ? (
          <TranscriptBlock
            transcript={transcript}
            onEdit={onEditTranscript}
            onQuickAction={onQuickAction}
            quickActionsDisabled={actionBusy}
            audioSrc={audioSrc}
            audioDurationMs={audioDurationMs}
          />
        ) : null}
        {transcriptionJob &&
        transcriptionJob.status !== "succeeded" ? (
          <JobProgressInline kind="transcription" state={transcriptionJob} />
        ) : null}
        {messages.map((message) => {
          const pendingForThis =
            chatJob &&
            chatJob.status !== "succeeded" &&
            message.role === "assistant" &&
            (message.status === "queued" || message.status === "running")
              ? chatJob
              : null;
          return (
            <MessageBubble
              key={message.id}
              message={message}
              sessionId={sessionId}
              settings={settings}
              ttsStatus={ttsStatuses[message.id]}
              ttsBusy={ttsBusyMessageId === message.id}
              ttsAudioUrl={getTtsAudioUrl(message.id)}
              pendingJob={pendingForThis}
              actionBusy={actionBusy}
              onConfirmAction={onConfirmAction}
              onCancelAction={onCancelAction}
              onGenerateTts={() => onGenerateTts(message.id)}
            />
          );
        })}
        {chatJob &&
        chatJob.status !== "succeeded" &&
        messages.findIndex((m) => m.status === "queued" || m.status === "running") === -1 ? (
          <JobProgressInline kind="chat" state={chatJob} />
        ) : null}
        <div ref={endRef} />
      </div>
    </ScrollArea>
  );
}
