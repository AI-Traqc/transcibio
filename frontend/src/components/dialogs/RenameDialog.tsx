import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { strings } from "@/lib/strings";
import type { SessionRecord } from "@/types/session";

interface RenameDialogProps {
  open: boolean;
  session: SessionRecord | null;
  busy: boolean;
  error: string | null;
  onOpenChange: (open: boolean) => void;
  onConfirm: (title: string) => void;
}

export function RenameDialog({
  open,
  session,
  busy,
  error,
  onOpenChange,
  onConfirm,
}: RenameDialogProps) {
  const [value, setValue] = useState("");

  useEffect(() => {
    if (open && session) {
      setValue(session.title || "");
    }
  }, [open, session]);

  const trimmed = value.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{strings.dialogs.rename.title}</DialogTitle>
          <DialogDescription>
            {session ? `Session · ${session.id.slice(0, 8)}` : ""}
          </DialogDescription>
        </DialogHeader>
        <Input
          value={value}
          onChange={(event) => setValue(event.currentTarget.value)}
          placeholder={strings.dialogs.rename.placeholder}
          maxLength={200}
          autoFocus
          onKeyDown={(event) => {
            if (event.key === "Enter" && trimmed && !busy) {
              event.preventDefault();
              onConfirm(trimmed);
            }
          }}
        />
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            {strings.dialogs.rename.cancel}
          </Button>
          <Button
            onClick={() => onConfirm(trimmed)}
            disabled={!trimmed || busy}
          >
            {strings.dialogs.rename.confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
