import { Quote } from "lucide-react";
import type { ChatCitation } from "@/types/chat";

function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

interface CitationListProps {
  citations: ChatCitation[];
  showTimestamps: boolean;
}

export function CitationList({ citations, showTimestamps }: CitationListProps) {
  if (citations.length === 0) return null;
  return (
    <div className="mt-3 space-y-1.5">
      {citations.map((c) => (
        <div
          key={c.id}
          className="flex items-start gap-2 rounded-md bg-muted/60 px-3 py-2 text-xs text-muted-foreground"
        >
          <Quote className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <div className="min-w-0 flex-1">
            {showTimestamps ? (
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/70">
                {formatClock(c.start_ms)} – {formatClock(c.end_ms)}
              </span>
            ) : null}
            <p className="line-clamp-2 text-xs">{c.quote_excerpt}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
