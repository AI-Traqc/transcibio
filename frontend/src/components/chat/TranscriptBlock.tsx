import { useState } from "react";
import { ChevronDown, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/cn";
import { strings } from "@/lib/strings";
import { AudioPlayer } from "./AudioPlayer";
import { QuickActions } from "./QuickActions";
import type { TranscriptResponse } from "@/types/transcript";

function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

interface TranscriptBlockProps {
  transcript: TranscriptResponse;
  onEdit: () => void;
  onQuickAction: (prompt: string) => void;
  quickActionsDisabled?: boolean;
  audioSrc?: string | null;
  audioDurationMs?: number;
}

export function TranscriptBlock({
  transcript,
  onEdit,
  onQuickAction,
  quickActionsDisabled,
  audioSrc,
  audioDurationMs,
}: TranscriptBlockProps) {
  const [open, setOpen] = useState(false);
  const segments = transcript.segments;
  const speakerCount = transcript.speakers.length;

  return (
    <div className="mx-4 my-4 animate-fade-in rounded-lg border bg-card text-card-foreground shadow-sm md:mx-8">
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="flex items-center gap-2 px-4 py-3">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex flex-1 items-center gap-2 text-left"
            >
              <ChevronDown
                className={cn(
                  "h-4 w-4 text-muted-foreground transition-transform",
                  open && "rotate-180",
                )}
              />
              <span className="text-sm font-medium">
                {strings.chat.transcriptBlockTitle}
              </span>
              <span className="text-xs text-muted-foreground">
                · {segments.length} segments · {speakerCount} speakers
              </span>
            </button>
          </CollapsibleTrigger>
          <Button size="sm" variant="outline" onClick={onEdit}>
            <Pencil />
            <span>{strings.chat.transcriptBlockEdit}</span>
          </Button>
        </div>
        {audioSrc ? (
          <div className="border-t px-4 py-2">
            <AudioPlayer src={audioSrc} durationMs={audioDurationMs ?? 0} />
          </div>
        ) : null}
        <CollapsibleContent>
          <div className="max-h-72 space-y-2 overflow-y-auto border-t px-4 py-3 text-sm scrollbar-thin">
            {segments.map((segment) => (
              <div key={segment.id} className="flex gap-3">
                <span className="shrink-0 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                  {formatClock(segment.start_ms)}
                </span>
                <div className="min-w-0 flex-1">
                  {segment.speaker_display_name ? (
                    <span className="text-xs font-semibold text-primary">
                      {segment.speaker_display_name}:{" "}
                    </span>
                  ) : null}
                  <span className="whitespace-pre-wrap">{segment.text}</span>
                </div>
              </div>
            ))}
          </div>
        </CollapsibleContent>
      </Collapsible>
      <div className="border-t px-4 py-3">
        <QuickActions onTrigger={onQuickAction} disabled={quickActionsDisabled} />
      </div>
    </div>
  );
}
