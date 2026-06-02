import { Loader2, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { TtsStatusResponse } from "@/types/tts";

interface TtsBarProps {
  messageId: string;
  status: TtsStatusResponse | undefined;
  busy: boolean;
  onGenerate: () => void;
  audioUrl: string;
}

export function TtsBar({
  status,
  busy,
  onGenerate,
  audioUrl,
}: TtsBarProps) {
  const ready = status?.status === "completed";
  const failed = status?.status === "failed";

  return (
    <div className="mt-3 flex items-center gap-2">
      {ready ? (
        <audio controls preload="none" src={audioUrl} className="h-8" />
      ) : (
        <Button
          size="sm"
          variant="outline"
          onClick={onGenerate}
          disabled={busy}
        >
          {busy ? <Loader2 className="animate-spin" /> : <Volume2 />}
          <span>{busy ? "Generating…" : "Play"}</span>
        </Button>
      )}
      {failed && status?.error_message ? (
        <span className="text-xs text-destructive">{status.error_message}</span>
      ) : null}
    </div>
  );
}
