import { cn } from "@/lib/cn";
import type { RecordingState } from "@/types/session";
import { AttachMenu } from "./AttachMenu";
import { ComposerInput } from "./ComposerInput";
import { MicButton } from "./MicButton";
import { SendButton } from "./SendButton";

interface ComposerProps {
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  onFile: (file: File) => void;
  onStartMeetingRecording: () => void;
  onStopMeetingRecording: () => void;
  meetingRecordingState: RecordingState;
  meetingElapsedMs: number;
  commandRecordingState: RecordingState;
  commandElapsedMs: number;
  onStartCommand: () => void;
  onStopCommand: () => void;
  disabled?: boolean;
  commandDisabled?: boolean;
  busy?: boolean;
  children?: React.ReactNode;
}

export function Composer({
  draft,
  onDraftChange,
  onSubmit,
  onFile,
  onStartMeetingRecording,
  onStopMeetingRecording,
  meetingRecordingState,
  meetingElapsedMs,
  commandRecordingState,
  commandElapsedMs,
  onStartCommand,
  onStopCommand,
  disabled,
  commandDisabled,
  busy,
  children,
}: ComposerProps) {
  const canSend = !disabled && !busy && draft.trim().length > 0;
  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-4 pt-2">
      {children}
      <div
        className={cn(
          "flex items-end gap-2 rounded-2xl border bg-background px-3 py-2 shadow-sm transition-colors",
          disabled && "opacity-60",
        )}
      >
        <AttachMenu
          onFile={onFile}
          onStartMeetingRecording={onStartMeetingRecording}
          onStopMeetingRecording={onStopMeetingRecording}
          meetingRecordingState={meetingRecordingState}
          meetingElapsedMs={meetingElapsedMs}
          disabled={disabled}
        />
        <div className="flex-1">
          <ComposerInput
            value={draft}
            onChange={onDraftChange}
            onSubmit={onSubmit}
            disabled={disabled}
          />
        </div>
        <MicButton
          state={commandRecordingState}
          elapsedMs={commandElapsedMs}
          onStart={onStartCommand}
          onStop={onStopCommand}
          disabled={disabled || commandDisabled}
        />
        <SendButton
          onClick={onSubmit}
          disabled={!canSend}
          busy={busy}
        />
      </div>
    </div>
  );
}
