import { Loader2, Mic, Volume2 } from "lucide-react";
import type { ConversationPhase } from "@/hooks/useVadConversation";
import type { VoiceEngine } from "@/types/settings";

const ENGINE_LABEL: Record<VoiceEngine, string> = {
  piper: "Piper · Deutsch",
  kokoro: "Kokoro · English",
};

interface VoiceModeBarProps {
  enabled: boolean;
  onToggle: () => void;
  engine: VoiceEngine;
  phase: ConversationPhase;
  streamingText: string;
  error: string | null;
}

export function VoiceModeBar({
  enabled,
  onToggle,
  engine,
  phase,
  streamingText,
  error,
}: VoiceModeBarProps) {
  return (
    <div className="flex items-center gap-3 border-t px-3 py-2 text-sm">
      <button
        type="button"
        onClick={onToggle}
        aria-pressed={enabled}
        className={`flex items-center gap-1.5 rounded-full px-3 py-1 font-medium transition ${
          enabled
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground hover:bg-muted/80"
        }`}
      >
        <Volume2 className="h-4 w-4" />
        Sprachmodus
      </button>

      {enabled ? (
        <span className="text-xs text-muted-foreground">{ENGINE_LABEL[engine]}</span>
      ) : null}

      <div className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
        {error ? (
          <span className="text-destructive">{error}</span>
        ) : !enabled ? (
          <span>Freihändiges Gespräch — einschalten und einfach sprechen.</span>
        ) : phase === "speaking" ? (
          <span className="flex items-center gap-1.5">
            <Volume2 className="h-3.5 w-3.5 shrink-0 text-primary" />
            <span className="truncate">{streamingText || "Spricht…"}</span>
          </span>
        ) : phase === "listening" ? (
          <span className="flex items-center gap-1.5">
            <Mic className="h-3.5 w-3.5 shrink-0 text-primary" />
            Zuhören… sprechen Sie einfach los.
          </span>
        ) : (
          <span className="flex items-center gap-1.5">
            <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
            {phase === "transcribing" ? "Erkenne Sprache…" : "Startet…"}
          </span>
        )}
      </div>
    </div>
  );
}
