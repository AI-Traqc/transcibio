import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { strings } from "@/lib/strings";
import type { JobUiState } from "@/types/job";

interface JobProgressInlineProps {
  kind: "transcription" | "chat";
  state: JobUiState;
}

const TRANSCRIPTION_STAGE_LABELS: Record<string, string> = {
  stt: "Transcribing audio…",
  stt_complete: "Speech-to-text complete",
  diarization: "Identifying speakers…",
  diarization_complete: "Speakers identified",
  alignment: "Aligning segments…",
  transcript_persisted: "Saving transcript…",
};

const CHAT_STAGE_LABELS: Record<string, string> = {
  "chat.retrieval.started": "Searching the transcript…",
  "chat.retrieval.completed": "Found relevant passages",
  "chat.generation.started": "Generating reply…",
  "chat.generation.completed": "Polishing reply…",
  "chat.citations.ready": "Citing passages…",
  "chat.action_proposals.ready": "Preparing actions…",
};

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function JobProgressInline({ kind, state }: JobProgressInlineProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(id);
  }, []);

  const pct = Math.max(0, Math.min(100, Math.round(state.progress * 100)));
  const elapsed = state.startedAt ? now - state.startedAt : 0;

  const fallbackLabel =
    kind === "transcription"
      ? strings.status.transcribing
      : "Generating reply…";

  const stageLabel =
    state.stageMessage ||
    (state.stage &&
      (kind === "transcription"
        ? TRANSCRIPTION_STAGE_LABELS[state.stage]
        : CHAT_STAGE_LABELS[state.stage])) ||
    fallbackLabel;

  return (
    <div className="mx-4 my-4 rounded-lg border bg-card p-4 text-card-foreground shadow-sm md:mx-8">
      <div className="flex items-center gap-3">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
        <span className="text-sm font-medium">{stageLabel}</span>
        <span className="ml-auto flex items-center gap-3 text-xs font-mono text-muted-foreground">
          {state.startedAt ? <span>{formatElapsed(elapsed)}</span> : null}
          <span>{pct}%</span>
        </span>
      </div>
      <Progress value={pct} className="mt-3 h-1.5" />
      {state.errorMessage ? (
        <p className="mt-2 text-xs text-destructive">{state.errorMessage}</p>
      ) : null}
    </div>
  );
}
