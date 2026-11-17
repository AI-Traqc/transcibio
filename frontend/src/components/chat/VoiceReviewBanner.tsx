import { Mic, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { strings } from "@/lib/strings";

interface VoiceReviewBannerProps {
  onDiscard: () => void;
}

export function VoiceReviewBanner({ onDiscard }: VoiceReviewBannerProps) {
  return (
    <div className="flex items-center gap-3 rounded-md bg-primary/10 px-3 py-2 text-sm">
      <Mic className="h-4 w-4 text-primary" />
      <div className="flex-1">
        <p className="font-medium">{strings.composer.voiceReview.title}</p>
        <p className="text-xs text-muted-foreground">
          {strings.composer.voiceReview.description}
        </p>
      </div>
      <Button
        size="sm"
        variant="ghost"
        onClick={onDiscard}
        aria-label={strings.composer.voiceReview.dismiss}
      >
        <X />
      </Button>
    </div>
  );
}
