import { useRef } from "react";
import { Disc, FileAudio, Plus, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { RecordingState } from "@/types/session";

interface AttachMenuProps {
  onFile: (file: File) => void;
  onStartMeetingRecording: () => void;
  onStopMeetingRecording: () => void;
  meetingRecordingState: RecordingState;
  meetingElapsedMs: number;
  // Longest recording the transcription engine accepts (Nemotron: 60 min); null = no limit.
  meetingMaxMs?: number | null;
  disabled?: boolean;
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function AttachMenu({
  onFile,
  onStartMeetingRecording,
  onStopMeetingRecording,
  meetingRecordingState,
  meetingElapsedMs,
  meetingMaxMs = null,
  disabled,
}: AttachMenuProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const recording = meetingRecordingState === "recording";
  const overMax = meetingMaxMs !== null && meetingElapsedMs > meetingMaxMs;

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".mp3,.wav,audio/mpeg,audio/wav"
        className="hidden"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (file) onFile(file);
          event.currentTarget.value = "";
        }}
      />
      {recording ? (
        <Button
          type="button"
          variant="destructive"
          size="default"
          onClick={onStopMeetingRecording}
          aria-label="Stop recording"
          title={
            meetingMaxMs === null
              ? undefined
              : overMax
                ? "Over 60 minutes: Nemotron can't transcribe this. Switch to Whisper in Settings."
                : "Nemotron transcribes recordings up to 60 minutes."
          }
        >
          <Square />
          <span className="font-mono text-xs">
            {formatElapsed(meetingElapsedMs)}
            {meetingMaxMs !== null ? ` / ${formatElapsed(meetingMaxMs)}` : null}
          </span>
        </Button>
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={disabled}
              aria-label="Attach audio"
            >
              <Plus />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onClick={() => inputRef.current?.click()}>
              <FileAudio />
              <span>Upload meeting audio</span>
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onStartMeetingRecording}>
              <Disc />
              <span>Record meeting</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </>
  );
}
