import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { strings } from "@/lib/strings";
import type { SessionRecord } from "@/types/session";

interface DeleteDialogProps {
  open: boolean;
  session: SessionRecord | null;
  busy: boolean;
  error: string | null;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function DeleteDialog({
  open,
  session,
  busy,
  error,
  onOpenChange,
  onConfirm,
}: DeleteDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{strings.dialogs.delete.title}</DialogTitle>
          <DialogDescription>
            {strings.dialogs.delete.description}
            {session ? (
              <span className="mt-2 block font-medium text-foreground">
                {session.title || "Untitled"}
              </span>
            ) : null}
          </DialogDescription>
        </DialogHeader>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            {strings.dialogs.delete.cancel}
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={busy}
          >
            {strings.dialogs.delete.confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
