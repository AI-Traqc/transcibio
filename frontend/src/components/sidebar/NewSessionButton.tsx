import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { strings } from "@/lib/strings";

interface NewSessionButtonProps {
  onClick: () => void;
  disabled?: boolean;
}

export function NewSessionButton({ onClick, disabled }: NewSessionButtonProps) {
  return (
    <Button
      variant="secondary"
      className="w-full justify-start gap-2"
      onClick={onClick}
      disabled={disabled}
    >
      <Plus />
      <span>{strings.sidebar.newSession}</span>
    </Button>
  );
}
