import { Check, Download, FileText, X } from "lucide-react";
import { artifactDownloadUrl } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { ChatActionProposal } from "@/types/chat";

type Variant = "default" | "secondary" | "destructive" | "success" | "warning";

function statusVariant(status: string): Variant {
  switch (status) {
    case "completed":
      return "success";
    case "executing":
    case "confirmed":
      return "default";
    case "failed":
      return "destructive";
    case "cancelled":
      return "secondary";
    default:
      return "secondary";
  }
}

interface ActionCardProps {
  action: ChatActionProposal;
  sessionId: string;
  onConfirm?: (actionId: string) => void;
  onCancel?: (actionId: string) => void;
  busy?: boolean;
}

export function ActionCard({
  action,
  sessionId,
  onConfirm,
  onCancel,
  busy,
}: ActionCardProps) {
  const pending = action.status === "proposed";
  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-3 text-card-foreground shadow-sm",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <span className="truncate text-sm font-medium">{action.title}</span>
          </div>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span className="font-mono">{action.action_type}</span>
            <Badge variant={statusVariant(action.status)}>
              {action.status}
            </Badge>
          </div>
        </div>
      </div>

      {action.preview_markdown ? (
        <pre className="mt-2 whitespace-pre-wrap rounded-md bg-muted/60 px-3 py-2 font-mono text-xs text-muted-foreground">
          {action.preview_markdown}
        </pre>
      ) : null}

      {action.error_message ? (
        <p className="mt-2 text-xs text-destructive">{action.error_message}</p>
      ) : null}

      {action.artifacts.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {action.artifacts.map((artifact) => (
            <li key={artifact.id}>
              <a
                href={artifactDownloadUrl(sessionId, artifact.id)}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline"
              >
                <Download className="h-3.5 w-3.5" />
                <span>{artifact.file_name}</span>
              </a>
            </li>
          ))}
        </ul>
      ) : null}

      {pending ? (
        <div className="mt-3 flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => onConfirm?.(action.id)}
            disabled={busy}
          >
            <Check />
            <span>Confirm</span>
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onCancel?.(action.id)}
            disabled={busy}
          >
            <X />
            <span>Cancel</span>
          </Button>
        </div>
      ) : null}
    </div>
  );
}
