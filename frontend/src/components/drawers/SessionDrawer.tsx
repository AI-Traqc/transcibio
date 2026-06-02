import { Disc, FileAudio, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { AudioUploadResponse, RecordingState, SessionRecord } from "@/types/session";
import type { JobUiState } from "@/types/job";

interface SessionDrawerProps {
  open: boolean;
  session: SessionRecord | null;
  audio: AudioUploadResponse | null;
  meetingRecordingState: RecordingState;
  transcriptionJob: JobUiState | null;
  onOpenChange: (open: boolean) => void;
  onUploadClick: () => void;
  onToggleMeetingRecording: () => void;
}

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "—";
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export function SessionDrawer({
  open,
  session,
  audio,
  meetingRecordingState,
  transcriptionJob,
  onOpenChange,
  onUploadClick,
  onToggleMeetingRecording,
}: SessionDrawerProps) {
  const recording = meetingRecordingState === "recording";
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Session details</SheetTitle>
          <SheetDescription>
            {session ? session.title : "No session selected"}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-6">
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Meeting audio
            </h3>
            <div className="mt-2 space-y-2">
              <Button
                variant="outline"
                className="w-full justify-start gap-2"
                onClick={onUploadClick}
                disabled={!session}
              >
                <FileAudio />
                <span>Upload audio file</span>
              </Button>
              <Button
                variant="outline"
                className="w-full justify-start gap-2"
                onClick={onToggleMeetingRecording}
                disabled={!session}
              >
                <Disc />
                <span>{recording ? "Stop recording" : "Record meeting"}</span>
              </Button>
            </div>
            {audio ? (
              <dl className="mt-3 space-y-1 text-xs">
                <div className="flex justify-between text-muted-foreground">
                  <dt>File</dt>
                  <dd className="font-mono text-foreground">{audio.file_name}</dd>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <dt>Duration</dt>
                  <dd>{formatDuration(audio.duration_ms)}</dd>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <dt>Type</dt>
                  <dd>{audio.mime_type}</dd>
                </div>
              </dl>
            ) : null}
          </section>

          {transcriptionJob ? (
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Transcription
              </h3>
              <div className="mt-2 rounded-md border p-3">
                <div className="flex items-center gap-2 text-sm">
                  {transcriptionJob.status === "running" ||
                  transcriptionJob.status === "queued" ? (
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                  ) : null}
                  <span className="capitalize">{transcriptionJob.status}</span>
                  <span className="ml-auto font-mono text-xs text-muted-foreground">
                    {Math.round(transcriptionJob.progress * 100)}%
                  </span>
                </div>
                <Progress
                  value={Math.round(transcriptionJob.progress * 100)}
                  className="mt-2 h-1.5"
                />
                {transcriptionJob.errorMessage ? (
                  <p className="mt-2 text-xs text-destructive">
                    {transcriptionJob.errorMessage}
                  </p>
                ) : null}
              </div>
            </section>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
