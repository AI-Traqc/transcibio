import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { SessionItem } from "./SessionItem";
import { strings } from "@/lib/strings";
import type { SessionRecord } from "@/types/session";

interface SessionListProps {
  sessions: SessionRecord[];
  selectedSessionId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onRename: (session: SessionRecord) => void;
  onDelete: (session: SessionRecord) => void;
}

export function SessionList({
  sessions,
  selectedSessionId,
  loading,
  onSelect,
  onRename,
  onDelete,
}: SessionListProps) {
  if (loading && sessions.length === 0) {
    return (
      <div className="space-y-1 px-1">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <p className="px-3 py-4 text-sm text-muted-foreground">
        {strings.sidebar.empty}
      </p>
    );
  }

  return (
    <ScrollArea className="h-full scrollbar-thin">
      <div className="space-y-0.5 px-1 pb-2">
        {sessions.map((session) => (
          <SessionItem
            key={session.id}
            session={session}
            selected={session.id === selectedSessionId}
            onSelect={() => onSelect(session.id)}
            onRename={() => onRename(session)}
            onDelete={() => onDelete(session)}
          />
        ))}
      </div>
    </ScrollArea>
  );
}
