import { Button } from "@/components/ui/button";
import { strings } from "@/lib/strings";

interface QuickActionsProps {
  onTrigger: (prompt: string) => void;
  disabled?: boolean;
}

const PROMPTS: Array<{ key: keyof typeof strings.chat.quickActions; prompt: string }> = [
  { key: "summarize", prompt: "Fasse die wichtigsten Entscheidungen aus dem Transkript zusammen." },
  {
    key: "keyPoints",
    prompt: "Extrahiere die 5 wichtigsten Punkte als Aufzählung.",
  },
  {
    key: "identifySpeakers",
    prompt: "Versuche die Sprecher anhand ihrer Aussagen zu identifizieren. Schlage Bezeichnungen vor.",
  },
  {
    key: "translate",
    prompt: "Übersetze das Transkript ins Englische.",
  },
];

export function QuickActions({ onTrigger, disabled }: QuickActionsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {PROMPTS.map(({ key, prompt }) => (
        <Button
          key={key}
          variant="outline"
          size="sm"
          onClick={() => onTrigger(prompt)}
          disabled={disabled}
        >
          {strings.chat.quickActions[key]}
        </Button>
      ))}
    </div>
  );
}
