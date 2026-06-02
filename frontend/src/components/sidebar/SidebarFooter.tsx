import { Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ThemeToggle } from "./ThemeToggle";
import { strings } from "@/lib/strings";

interface SidebarFooterProps {
  onOpenSettings: () => void;
}

export function SidebarFooter({ onOpenSettings }: SidebarFooterProps) {
  return (
    <div className="border-t px-2 py-2">
      <Separator className="mb-2" />
      <div className="flex items-center justify-between">
        <Button
          variant="ghost"
          className="flex-1 justify-start gap-2"
          onClick={onOpenSettings}
        >
          <Settings />
          <span>{strings.sidebar.settings}</span>
        </Button>
        <ThemeToggle />
      </div>
    </div>
  );
}
