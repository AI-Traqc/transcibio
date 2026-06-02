import { MessageSquareText, Mic, Sparkles, Upload } from "lucide-react";
import { strings } from "@/lib/strings";

type Variant = "no-session" | "no-audio" | "ready";

interface EmptyStateProps {
  variant: Variant;
  onNewSession?: () => void;
  onUpload?: () => void;
}

export function EmptyState({ variant, onNewSession, onUpload }: EmptyStateProps) {
  if (variant === "no-session") {
    const copy = strings.chat.emptyNoSession;
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <div className="rounded-full bg-muted p-4">
          <MessageSquareText className="h-8 w-8 text-muted-foreground" />
        </div>
        <h2 className="mt-4 text-lg font-semibold">{copy.title}</h2>
        <p className="mt-1 max-w-md text-sm text-muted-foreground">
          {copy.subtitle}
        </p>
        {onNewSession ? (
          <button
            type="button"
            onClick={onNewSession}
            className="mt-4 text-sm font-medium text-primary hover:underline"
          >
            {strings.sidebar.newSession}
          </button>
        ) : null}
      </div>
    );
  }

  if (variant === "no-audio") {
    const copy = strings.chat.emptyNoAudio;
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <div className="rounded-full bg-muted p-4">
          <Upload className="h-8 w-8 text-muted-foreground" />
        </div>
        <h2 className="mt-4 text-lg font-semibold">{copy.title}</h2>
        <p className="mt-1 max-w-md text-sm text-muted-foreground">
          {copy.subtitle}
        </p>
        {onUpload ? (
          <button
            type="button"
            onClick={onUpload}
            className="mt-4 text-sm font-medium text-primary hover:underline"
          >
            {strings.chat.attach}
          </button>
        ) : null}
      </div>
    );
  }

  const copy = strings.chat.emptyReady;
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="flex items-center gap-2 rounded-full bg-muted px-4 py-1.5 text-xs font-medium text-muted-foreground">
        <Sparkles className="h-3.5 w-3.5" />
        <span>{strings.status.ready}</span>
      </div>
      <h2 className="mt-4 text-lg font-semibold">{copy.title}</h2>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">
        {copy.subtitle}
      </p>
      <p className="mt-6 flex items-center gap-1.5 text-xs text-muted-foreground">
        <Mic className="h-3 w-3" />
        <span>{strings.chat.voice}</span>
      </p>
    </div>
  );
}
