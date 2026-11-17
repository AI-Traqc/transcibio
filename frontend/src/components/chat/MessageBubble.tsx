import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/cn";
import { strings } from "@/lib/strings";
import { ActionCard } from "./ActionCard";
import { CitationList } from "./CitationList";
import { TtsBar } from "./TtsBar";
import type { ChatMessage } from "@/types/chat";
import type { JobUiState } from "@/types/job";
import type { SettingsPayload } from "@/types/settings";
import type { TtsStatusResponse } from "@/types/tts";

interface MessageBubbleProps {
  message: ChatMessage;
  sessionId: string;
  settings: SettingsPayload | null;
  ttsStatus: TtsStatusResponse | undefined;
  ttsBusy: boolean;
  ttsAudioUrl: string;
  pendingJob?: JobUiState | null;
  onConfirmAction?: (actionId: string) => void;
  onCancelAction?: (actionId: string) => void;
  onGenerateTts?: () => void;
  actionBusy?: boolean;
}

const CHAT_STAGE_LABELS: Record<string, string> = {
  "chat.retrieval.started": "Searching the transcript\u2026",
  "chat.retrieval.completed": "Found relevant passages",
  "chat.llm.started": "Thinking\u2026",
  "chat.llm.completed": "Polishing reply\u2026",
  "chat.citations.ready": "Citing passages\u2026",
  "chat.action_proposals.ready": "Preparing actions\u2026",
  "chat.assistant.completed": "Finalizing\u2026",
  // Backwards-compat with any emitters that use the *.generation names.
  "chat.generation.started": "Thinking\u2026",
  "chat.generation.completed": "Polishing reply\u2026",
};

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function MessageBubble({
  message,
  sessionId,
  settings,
  ttsStatus,
  ttsBusy,
  ttsAudioUrl,
  pendingJob,
  onConfirmAction,
  onCancelAction,
  onGenerateTts,
  actionBusy,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isRunning = message.status === "queued" || message.status === "running";
  const showTts = settings?.tts.enabled ?? false;
  const showTimestamps = settings?.ui.show_timestamps_in_citations ?? false;
  const hasBody =
    (message.content_markdown ?? "").trim().length > 0 ||
    (message.content_plain_text ?? "").trim().length > 0;
  const shouldBindJob = isRunning && !isUser && !!pendingJob;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!shouldBindJob) return;
    const id = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(id);
  }, [shouldBindJob]);
  const stageLabel =
    (pendingJob?.stageMessage ||
      (pendingJob?.stage ? CHAT_STAGE_LABELS[pendingJob.stage] : null)) ??
    "Generating response\u2026";
  const elapsedMs = pendingJob?.startedAt ? now - pendingJob.startedAt : 0;
  const pct = pendingJob
    ? Math.max(0, Math.min(100, Math.round(pendingJob.progress * 100)))
    : 0;

  return (
    <article
      className={cn(
        "flex w-full animate-fade-in gap-3 px-4 py-5 md:px-8",
        isUser ? "bg-background" : "bg-muted/40",
      )}
    >
      <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold uppercase text-primary">
        {isUser ? "U" : "P"}
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1.5 text-xs font-medium text-muted-foreground">
          {isUser ? strings.chat.you : strings.chat.assistant}
        </div>
        {hasBody ? (
          isUser ? (
            <div className="prose prose-sm max-w-none whitespace-pre-wrap text-foreground dark:prose-invert">
              {message.content_markdown || message.content_plain_text}
            </div>
          ) : (
            <div className="prose prose-sm max-w-none text-foreground dark:prose-invert">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content_markdown || message.content_plain_text || ""}
              </ReactMarkdown>
            </div>
          )
        ) : isRunning ? (
          <div className="flex flex-col gap-2 text-sm text-muted-foreground">
            <div className="inline-flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>{stageLabel}</span>
              {pendingJob ? (
                <span className="ml-2 font-mono text-xs">
                  {pendingJob.startedAt ? formatElapsed(elapsedMs) : null}
                  {pct > 0 ? ` · ${pct}%` : null}
                </span>
              ) : null}
            </div>
            {pendingJob && pct > 0 ? (
              <div className="h-1 w-40 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full bg-primary transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
            ) : null}
          </div>
        ) : null}

        {!isUser && message.citations.length > 0 ? (
          <CitationList
            citations={message.citations}
            showTimestamps={showTimestamps}
          />
        ) : null}

        {!isUser && message.action_proposals.length > 0 ? (
          <div className="mt-3 space-y-2">
            {message.action_proposals.map((action) => (
              <ActionCard
                key={action.id}
                action={action}
                sessionId={sessionId}
                busy={actionBusy}
                onConfirm={onConfirmAction}
                onCancel={onCancelAction}
              />
            ))}
          </div>
        ) : null}

        {!isUser && showTts && message.status === "completed" && onGenerateTts ? (
          <TtsBar
            messageId={message.id}
            status={ttsStatus}
            busy={ttsBusy}
            onGenerate={onGenerateTts}
            audioUrl={ttsAudioUrl}
          />
        ) : null}
      </div>
    </article>
  );
}
