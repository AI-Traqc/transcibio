import { Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { strings } from "@/lib/strings";
import type { SessionRecord } from "@/types/session";

interface ChatHeaderProps {
  session: SessionRecord | null;
  onOpenDrawer: () => void;
}

export function ChatHeader({ session, onOpenDrawer }: ChatHeaderProps) {
  return (
    <header className="flex items-center justify-between border-b bg-background px-4 py-3 md:px-8">
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-base font-semibold">
          {session ? session.title || "Untitled session" : strings.appName}
        </h1>
      </div>
      {session ? (
        <Button variant="ghost" size="sm" onClick={onOpenDrawer}>
          <Info />
          <span className="hidden sm:inline">{strings.drawers.session.title}</span>
        </Button>
      ) : null}
    </header>
  );
}
