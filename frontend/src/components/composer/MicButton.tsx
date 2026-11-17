import { Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { RecordingState } from "@/types/session";

interface MicButtonProps {
  state: RecordingState;
  elapsedMs: number;
  onStart: () => void;
  onStop: () => void;
  disabled?: boolean;
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function MicButton({
  state,
  elapsedMs,
  onStart,
  onStop,
  disabled,
}: MicButtonProps) {
  const recording = state === "recording";
  return (
    <Button
      type="button"
      variant={recording ? "destructive" : "ghost"}
      size={recording ? "default" : "icon"}
      onClick={recording ? onStop : onStart}
      disabled={
        state === "requesting" ||
        state === "uploading" ||
        (!recording && !!disabled)
      }
      aria-label={recording ? "Stop recording" : "Start voice command"}
    >
      {recording ? (
        <>
          <Square />
          <span className="font-mono text-xs">{formatElapsed(elapsedMs)}</span>
        </>
      ) : (
        <Mic />
      )}
    </Button>
  );
}
