import { ArrowUp, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface SendButtonProps {
  onClick: () => void;
  disabled?: boolean;
  busy?: boolean;
}

export function SendButton({ onClick, disabled, busy }: SendButtonProps) {
  return (
    <Button
      type="button"
      size="icon"
      onClick={onClick}
      disabled={disabled || busy}
      aria-label="Send message"
    >
      {busy ? <Loader2 className="animate-spin" /> : <ArrowUp />}
    </Button>
  );
}
