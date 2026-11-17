import { forwardRef, type KeyboardEvent } from "react";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/cn";
import { strings } from "@/lib/strings";

interface ComposerInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  className?: string;
}

export const ComposerInput = forwardRef<HTMLTextAreaElement, ComposerInputProps>(
  function ComposerInput(
    { value, onChange, onSubmit, disabled, className },
    ref,
  ) {
    const handleKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (!disabled && value.trim()) {
          onSubmit();
        }
      }
    };

    return (
      <Textarea
        ref={ref}
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
        onKeyDown={handleKey}
        placeholder={strings.chat.placeholder}
        rows={1}
        disabled={disabled}
        className={cn(
          "max-h-40 min-h-[44px] resize-none border-0 bg-transparent px-0 py-2 text-base shadow-none focus-visible:ring-0 focus-visible:ring-offset-0",
          className,
        )}
      />
    );
  },
);
