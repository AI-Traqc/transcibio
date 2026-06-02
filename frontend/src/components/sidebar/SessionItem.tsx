import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/cn";
import { strings } from "@/lib/strings";
import type { SessionRecord } from "@/types/session";

interface SessionItemProps {
  session: SessionRecord;
  selected: boolean;
  onSelect: () => void;
  onRename: () => void;
  onDelete: () => void;
}

export function SessionItem({
  session,
  selected,
  onSelect,
  onRename,
  onDelete,
}: SessionItemProps) {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <div
          className={cn(
            "group flex items-center gap-1 rounded-md pr-1 text-sm transition-colors",
            selected
              ? "bg-accent text-accent-foreground"
              : "hover:bg-muted/60",
          )}
        >
          <button
            type="button"
            onClick={onSelect}
            className="flex-1 truncate py-2 pl-3 pr-1 text-left"
          >
            <span className="line-clamp-1">{session.title || "Untitled"}</span>
          </button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label="More"
                className={cn(
                  "rounded p-1 opacity-0 transition-opacity hover:bg-muted focus:opacity-100 group-hover:opacity-100",
                  selected && "opacity-100",
                )}
                onClick={(event) => event.stopPropagation()}
              >
                <MoreHorizontal className="h-4 w-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onRename}>
                <Pencil />
                <span>{strings.sidebar.rename}</span>
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={onDelete}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 />
                <span>{strings.sidebar.delete}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem onClick={onRename}>
          <Pencil />
          <span>{strings.sidebar.rename}</span>
        </ContextMenuItem>
        <ContextMenuItem
          onClick={onDelete}
          className="text-destructive focus:text-destructive"
        >
          <Trash2 />
          <span>{strings.sidebar.delete}</span>
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}
