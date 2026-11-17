import { useState } from "react";
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

// The backend reports a finished synthesis as "succeeded".
const READY_STATUSES = new Set(["succeeded", "completed"]);

export function TtsBar({
  status,
  busy,
  onGenerate,
  audioUrl,
}: TtsBarProps) {
  // Start playback right away when the audio was requested with the Play button.
  const [requested, setRequested] = useState(false);
  const ready = READY_STATUSES.has(status?.status ?? "");
  const failed = status?.status === "failed";

  return (
    <div className="mt-3 flex items-center gap-2">
      {ready ? (
        <audio
          controls
          preload="none"
          autoPlay={requested}
          src={audioUrl}
          className="h-8"
          aria-label="Answer audio"
        />
      ) : (
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setRequested(true);
            onGenerate();
          }}
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
