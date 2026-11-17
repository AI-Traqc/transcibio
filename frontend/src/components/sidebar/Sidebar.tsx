import { PanelLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { strings } from "@/lib/strings";
import { SessionList } from "./SessionList";
import { SearchBar } from "./SearchBar";
import { NewSessionButton } from "./NewSessionButton";
import { SidebarFooter } from "./SidebarFooter";
import type { SessionRecord } from "@/types/session";

interface SidebarProps {
  sessions: SessionRecord[];
  selectedSessionId: string | null;
  loading: boolean;
  collapsed: boolean;
  query: string;
  onQueryChange: (q: string) => void;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onRenameSession: (session: SessionRecord) => void;
  onDeleteSession: (session: SessionRecord) => void;
  onToggleCollapse: () => void;
  onOpenSettings: () => void;
}

export function Sidebar({
  sessions,
  selectedSessionId,
  loading,
  collapsed,
  query,
  onQueryChange,
  onSelectSession,
  onNewSession,
  onRenameSession,
  onDeleteSession,
  onToggleCollapse,
  onOpenSettings,
}: SidebarProps) {
  if (collapsed) {
    return (
      <aside className="flex w-12 flex-col items-center gap-2 border-r bg-muted/30 py-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          aria-label={strings.sidebar.expand}
        >
          <PanelLeft />
        </Button>
      </aside>
    );
  }

  return (
    <aside
      className={cn(
        "flex h-full w-72 flex-col border-r bg-muted/30",
        "transition-all duration-200",
      )}
    >
      <div className="flex items-center justify-between px-3 py-3">
        <span className="text-sm font-semibold">{strings.appName}</span>
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          aria-label={strings.sidebar.collapse}
        >
          <PanelLeft />
        </Button>
      </div>
      <div className="space-y-2 px-2 pb-2">
        <NewSessionButton onClick={onNewSession} />
        <SearchBar value={query} onChange={onQueryChange} />
      </div>
      <div className="flex-1 overflow-hidden">
        <SessionList
          sessions={sessions}
          selectedSessionId={selectedSessionId}
          loading={loading}
          onSelect={onSelectSession}
          onRename={onRenameSession}
          onDelete={onDeleteSession}
        />
      </div>
      <SidebarFooter onOpenSettings={onOpenSettings} />
    </aside>
  );
}
