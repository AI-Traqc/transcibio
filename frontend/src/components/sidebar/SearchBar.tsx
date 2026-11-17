import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import { strings } from "@/lib/strings";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

export function SearchBar({ value, onChange, className }: SearchBarProps) {
  return (
    <div className={cn("relative", className)}>
      <Search
        className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        type="search"
        placeholder={strings.sidebar.searchPlaceholder}
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
        className="pl-8"
        aria-label={strings.sidebar.searchPlaceholder}
      />
    </div>
  );
}
