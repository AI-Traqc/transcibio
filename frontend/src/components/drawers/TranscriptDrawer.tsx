import { useEffect, useState } from "react";
import { Pencil, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { strings } from "@/lib/strings";
import type {
  TranscriptResponse,
  TranscriptSegment,
  TranscriptSpeaker,
} from "@/types/transcript";

interface TranscriptDrawerProps {
  open: boolean;
  transcript: TranscriptResponse | null;
  busy: boolean;
  error: string | null;
  onOpenChange: (open: boolean) => void;
  onSaveSegment: (segmentId: string, text: string) => Promise<void>;
  onSaveSpeaker: (speakerId: string, displayName: string) => Promise<void>;
}

function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function TranscriptDrawer({
  open,
  transcript,
  busy,
  error,
  onOpenChange,
  onSaveSegment,
  onSaveSpeaker,
}: TranscriptDrawerProps) {
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [segmentDraft, setSegmentDraft] = useState("");
  const [editingSpeakerId, setEditingSpeakerId] = useState<string | null>(null);
  const [speakerDraft, setSpeakerDraft] = useState("");

  useEffect(() => {
    if (!open) {
      setEditingSegmentId(null);
      setEditingSpeakerId(null);
    }
  }, [open]);

  const startEditSegment = (segment: TranscriptSegment) => {
    setEditingSegmentId(segment.id);
    setSegmentDraft(segment.text);
  };

  const startEditSpeaker = (speaker: TranscriptSpeaker) => {
    setEditingSpeakerId(speaker.id);
    setSpeakerDraft(speaker.display_name);
  };

  const saveSegment = async () => {
    if (!editingSegmentId) return;
    await onSaveSegment(editingSegmentId, segmentDraft);
    setEditingSegmentId(null);
  };

  const saveSpeaker = async () => {
    if (!editingSpeakerId) return;
    await onSaveSpeaker(editingSpeakerId, speakerDraft);
    setEditingSpeakerId(null);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>{strings.drawers.transcript.title}</SheetTitle>
          <SheetDescription>
            {transcript ? (
              <>
                Revision {transcript.revision.revision_number} ·{" "}
                {transcript.revision.source}
              </>
            ) : (
              "No transcript loaded"
            )}
          </SheetDescription>
        </SheetHeader>

        {error ? (
          <p className="mt-3 text-sm text-destructive">{error}</p>
        ) : null}

        {transcript ? (
          <Tabs defaultValue="segments" className="mt-4">
            <TabsList>
              <TabsTrigger value="segments">
                {strings.drawers.transcript.segments}
              </TabsTrigger>
              <TabsTrigger value="speakers">
                {strings.drawers.transcript.speakers}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="segments">
              <ScrollArea className="h-[calc(100vh-220px)] pr-2 scrollbar-thin">
                <div className="space-y-3 py-2">
                  {transcript.segments.map((segment) => (
                    <div
                      key={segment.id}
                      className="rounded-md border p-3 text-sm"
                    >
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span className="font-mono">
                          {formatClock(segment.start_ms)} – {formatClock(segment.end_ms)}
                        </span>
                        {segment.speaker_display_name ? (
                          <span className="font-medium text-primary">
                            {segment.speaker_display_name}
                          </span>
                        ) : null}
                      </div>
                      {editingSegmentId === segment.id ? (
                        <div className="mt-2 space-y-2">
                          <Textarea
                            value={segmentDraft}
                            onChange={(e) =>
                              setSegmentDraft(e.currentTarget.value)
                            }
                            rows={3}
                            autoFocus
                          />
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              onClick={saveSegment}
                              disabled={busy}
                            >
                              <Save />
                              <span>Save</span>
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setEditingSegmentId(null)}
                              disabled={busy}
                            >
                              <X />
                              <span>Cancel</span>
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-2 flex items-start gap-2">
                          <p className="flex-1 whitespace-pre-wrap">
                            {segment.text}
                          </p>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => startEditSegment(segment)}
                          >
                            <Pencil />
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </TabsContent>

            <TabsContent value="speakers">
              <div className="space-y-2 py-2">
                {transcript.speakers.map((speaker) => (
                  <div
                    key={speaker.id}
                    className="flex items-center gap-2 rounded-md border p-3 text-sm"
                  >
                    {editingSpeakerId === speaker.id ? (
                      <>
                        <Input
                          value={speakerDraft}
                          onChange={(e) =>
                            setSpeakerDraft(e.currentTarget.value)
                          }
                          autoFocus
                          className="flex-1"
                        />
                        <Button
                          size="sm"
                          onClick={saveSpeaker}
                          disabled={busy || !speakerDraft.trim()}
                        >
                          <Save />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setEditingSpeakerId(null)}
                        >
                          <X />
                        </Button>
                      </>
                    ) : (
                      <>
                        <div className="flex-1">
                          <div className="font-medium">
                            {speaker.display_name}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {speaker.speaker_key}
                          </div>
                        </div>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => startEditSpeaker(speaker)}
                        >
                          <Pencil />
                        </Button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            </TabsContent>
          </Tabs>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
