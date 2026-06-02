import { useEffect, useState } from "react";
import { Info, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { strings } from "@/lib/strings";
import * as settingsApi from "@/api/settings";
import type {
  ModelsResponse,
  ProcessingProfile,
  ResponseDetail,
  SettingsPatchRequest,
  SettingsPayload,
  VoiceEngine,
} from "@/types/settings";
import type { VoiceCommandSendMode } from "@/types/voice";

interface SettingsDialogProps {
  open: boolean;
  settings: SettingsPayload | null;
  busy: boolean;
  error: string | null;
  onOpenChange: (open: boolean) => void;
  onSave: (patch: SettingsPatchRequest) => Promise<void>;
  onDeleteAllSessions: () => Promise<void>;
}

function SettingLabel({ text, tooltip }: { text: string; tooltip: string }) {
  return (
    <div className="flex items-center gap-1">
      <Label>{text}</Label>
      <Tooltip>
        <TooltipTrigger asChild>
          <Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[220px]">
          <p>{tooltip}</p>
        </TooltipContent>
      </Tooltip>
    </div>
  );
}

function SwitchLabel({
  htmlFor,
  text,
  tooltip,
}: {
  htmlFor: string;
  text: string;
  tooltip: string;
}) {
  return (
    <div className="flex items-center gap-1">
      <Label htmlFor={htmlFor}>{text}</Label>
      <Tooltip>
        <TooltipTrigger asChild>
          <Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[220px]">
          <p>{tooltip}</p>
        </TooltipContent>
      </Tooltip>
    </div>
  );
}

export function SettingsDialog({
  open,
  settings,
  busy,
  error,
  onOpenChange,
  onSave,
  onDeleteAllSessions,
}: SettingsDialogProps) {
  const [profile, setProfile] = useState<ProcessingProfile>("balanced");
  const [sendMode, setSendMode] = useState<VoiceCommandSendMode>("review_then_send");
  const [detail, setDetail] = useState<ResponseDetail>("normal");
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [ttsAuto, setTtsAuto] = useState(false);
  const [ttsAutoplay, setTtsAutoplay] = useState(false);
  const [voiceEngine, setVoiceEngine] = useState<VoiceEngine>("piper");
  const [showTimestamps, setShowTimestamps] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [sttModel, setSttModel] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [diarizationEnabled, setDiarizationEnabled] = useState(true);

  useEffect(() => {
    if (!settings) return;
    setProfile(settings.processing_profile);
    setSendMode(settings.voice_commands.default_send_mode);
    setDetail(settings.chat.response_detail);
    setTtsEnabled(settings.tts.enabled);
    setTtsAuto(settings.tts.auto_generate_on_chat_reply);
    setTtsAutoplay(settings.tts.auto_play);
    setVoiceEngine(settings.tts.voice_engine);
    setShowTimestamps(settings.ui.show_timestamps_in_citations);
    setDiarizationEnabled(settings.stt.diarization_enabled_default);
    setConfirmDelete(false);
  }, [settings, open]);

  useEffect(() => {
    if (!open) return;
    setModelsLoading(true);
    settingsApi
      .getAvailableModels()
      .then((data) => {
        setModels(data);
        setSttModel(data.stt.current);
        setLlmModel(data.llm.current);
      })
      .catch(() => setModels(null))
      .finally(() => setModelsLoading(false));
  }, [open]);

  const handleDeleteAll = async () => {
    setDeleteBusy(true);
    try {
      await onDeleteAllSessions();
      setConfirmDelete(false);
    } finally {
      setDeleteBusy(false);
    }
  };

  const handleSave = async () => {
    await onSave({
      processing_profile: profile,
      stt: {
        diarization_enabled_default: diarizationEnabled,
        ...(sttModel ? { model: sttModel } : {}),
      },
      voice_commands: { default_send_mode: sendMode },
      chat: {
        response_detail: detail,
        ...(llmModel ? { model_name: llmModel } : {}),
      },
      tts: {
        enabled: ttsEnabled,
        auto_generate_on_chat_reply: ttsAuto,
        auto_play: ttsAutoplay,
        voice_engine: voiceEngine,
      },
      ui: { show_timestamps_in_citations: showTimestamps },
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{strings.dialogs.settings.title}</DialogTitle>
          <DialogDescription>
            {strings.dialogs.settings.description}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          <div className="space-y-3 rounded-md border p-3">
            <Label className="text-sm font-semibold">Models</Label>
            {modelsLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading available models...
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  <SettingLabel
                    text="Transcription model"
                    tooltip="Speech-to-text model. Larger models are more accurate but slower."
                  />
                  <Select value={sttModel} onValueChange={setSttModel}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select model" />
                    </SelectTrigger>
                    <SelectContent>
                      {(models?.stt.available ?? []).map((m) => (
                        <SelectItem key={m} value={m}>
                          {m}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <SettingLabel
                    text="Chat model (LLM)"
                    tooltip="The language model used for chat answers and transcript corrections."
                  />
                  {models?.llm.reachable === false ? (
                    <p className="text-xs text-destructive">
                      Ollama is not reachable. Start Ollama to select a model.
                    </p>
                  ) : (
                    <Select value={llmModel} onValueChange={setLlmModel}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select model" />
                      </SelectTrigger>
                      <SelectContent>
                        {(models?.llm.available ?? []).map((m) => (
                          <SelectItem key={m} value={m}>
                            {m}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>

                <div className="flex items-center justify-between">
                  <SwitchLabel
                    htmlFor="diarization-enabled"
                    text="Speaker diarization"
                    tooltip="Identifies different speakers in the audio. Requires a Hugging Face token."
                  />
                  <Switch
                    id="diarization-enabled"
                    checked={diarizationEnabled}
                    onCheckedChange={setDiarizationEnabled}
                  />
                </div>
              </>
            )}
          </div>

          <div className="space-y-2">
            <SettingLabel
              text="Processing profile"
              tooltip="Controls the speed vs. quality tradeoff for transcription."
            />
            <Select
              value={profile}
              onValueChange={(v) => setProfile(v as ProcessingProfile)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="fast">Fast</SelectItem>
                <SelectItem value="balanced">Balanced</SelectItem>
                <SelectItem value="quality">Quality</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <SettingLabel
              text="Voice command default"
              tooltip="Whether to review transcribed voice commands before sending them."
            />
            <Select
              value={sendMode}
              onValueChange={(v) => setSendMode(v as VoiceCommandSendMode)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="review_then_send">Review then send</SelectItem>
                <SelectItem value="auto_send">Auto-send</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <SettingLabel
              text="Response detail"
              tooltip="How detailed the AI responses should be."
            />
            <Select
              value={detail}
              onValueChange={(v) => setDetail(v as ResponseDetail)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="brief">Brief</SelectItem>
                <SelectItem value="normal">Normal</SelectItem>
                <SelectItem value="detailed">Detailed</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <SwitchLabel
                htmlFor="tts-enabled"
                text="TTS enabled"
                tooltip="Enable text-to-speech audio playback of AI responses."
              />
              <Switch
                id="tts-enabled"
                checked={ttsEnabled}
                onCheckedChange={setTtsEnabled}
              />
            </div>
            <div className="flex items-center justify-between">
              <SwitchLabel
                htmlFor="tts-auto"
                text="Auto-generate on reply"
                tooltip="Automatically generate speech when the AI replies."
              />
              <Switch
                id="tts-auto"
                checked={ttsAuto}
                onCheckedChange={setTtsAuto}
                disabled={!ttsEnabled}
              />
            </div>
            <div className="flex items-center justify-between">
              <SwitchLabel
                htmlFor="tts-play"
                text="Auto-play audio"
                tooltip="Automatically play generated speech audio."
              />
              <Switch
                id="tts-play"
                checked={ttsAutoplay}
                onCheckedChange={setTtsAutoplay}
                disabled={!ttsEnabled}
              />
            </div>
            <div className="space-y-2">
              <SettingLabel
                text="Voice-mode engine"
                tooltip="Streaming voice mode: Piper speaks German; Kokoro speaks English."
              />
              <Select
                value={voiceEngine}
                onValueChange={(v) => setVoiceEngine(v as VoiceEngine)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="piper">Piper — Deutsch</SelectItem>
                  <SelectItem value="kokoro">Kokoro — English</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <SwitchLabel
                htmlFor="show-timestamps"
                text="Show citation timestamps"
                tooltip="Display timestamps in transcript citations within chat."
              />
              <Switch
                id="show-timestamps"
                checked={showTimestamps}
                onCheckedChange={setShowTimestamps}
              />
            </div>
          </div>

          <div className="space-y-2 rounded-md border border-destructive/40 p-3">
            <Label className="text-destructive">Danger zone</Label>
            <p className="text-xs text-muted-foreground">
              Delete every session, its transcripts, chat history, and audio files. This cannot be undone.
            </p>
            {confirmDelete ? (
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleDeleteAll}
                  disabled={deleteBusy || busy}
                >
                  {deleteBusy ? "Deleting…" : "Confirm delete all"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirmDelete(false)}
                  disabled={deleteBusy}
                >
                  Cancel
                </Button>
              </div>
            ) : (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setConfirmDelete(true)}
                disabled={busy}
              >
                Delete all sessions
              </Button>
            )}
          </div>
        </div>

        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
