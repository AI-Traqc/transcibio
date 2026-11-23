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
  NemotronStatus,
  ProcessingProfile,
  ResponseDetail,
  SettingsPatchRequest,
  SettingsPayload,
  SttEngine,
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

// The Nemotron server needs a few minutes to load and warm up; the status refreshes itself
// while the dialog is open until the server runs.
const NEMOTRON_POLL_MS = 5000;

function formatElapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function NemotronServerStatus({
  status,
  loading,
}: {
  status: NemotronStatus | null;
  loading: boolean;
}) {
  if (loading && !status) {
    return <p className="text-muted-foreground">Checking server…</p>;
  }
  if (status?.state === "running") {
    return <p className="text-green-600 dark:text-green-500">Server is running.</p>;
  }
  if (status?.state === "starting") {
    const elapsed = status.starting_seconds ?? 0;
    return (
      <p className="flex items-start gap-1.5 text-amber-600 dark:text-amber-500" role="status">
        <Loader2 className="mt-0.5 h-3 w-3 shrink-0 animate-spin" />
        <span>
          Server is starting: loading the model and warming up ({formatElapsed(elapsed)}). This
          usually takes about 5 minutes; transcriptions work once it is running.
        </span>
      </p>
    );
  }
  return (
    <p className="text-destructive">
      Server is not running. To start it, add COMPOSE_PROFILES=nemotron to .env and restart
      the app.
    </p>
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
  const [llmModel, setLlmModel] = useState("");
  const [think, setThink] = useState(false);
  const [diarizationEnabled, setDiarizationEnabled] = useState(true);
  const [sttEngine, setSttEngine] = useState<SttEngine>("whisper-pyannote");
  const [nemotron, setNemotron] = useState<NemotronStatus | null>(null);

  useEffect(() => {
    if (!settings) return;
    // The Whisper model choice is the transcription preset the server applies to uploads.
    setProfile(settings.stt.default_preset ?? settings.processing_profile);
    setThink(settings.chat.think ?? false);
    setSendMode(settings.voice_commands.default_send_mode);
    setDetail(settings.chat.response_detail);
    setTtsEnabled(settings.tts.enabled);
    setTtsAuto(settings.tts.auto_generate_on_chat_reply);
    setTtsAutoplay(settings.tts.auto_play);
    setVoiceEngine(settings.tts.voice_engine);
    setShowTimestamps(settings.ui.show_timestamps_in_citations);
    setDiarizationEnabled(settings.stt.diarization_enabled_default);
    setSttEngine(settings.stt.engine ?? "whisper-pyannote");
    setConfirmDelete(false);
  }, [settings, open]);

  useEffect(() => {
    if (!open) return;
    setModelsLoading(true);
    settingsApi
      .getAvailableModels()
      .then((data) => {
        setModels(data);
        setLlmModel(data.llm.current);
        setNemotron(data.nemotron ?? null);
      })
      .catch(() => {
        setModels(null);
        setNemotron(null);
      })
      .finally(() => setModelsLoading(false));
  }, [open]);

  // Refresh only the Nemotron status (not the whole model list, which would reset choices).
  const nemotronState = nemotron?.state;
  useEffect(() => {
    if (!open || sttEngine !== "nemotron" || modelsLoading || nemotronState === "running") {
      return;
    }
    const timer = window.setInterval(() => {
      settingsApi
        .getNemotronStatus()
        .then(setNemotron)
        .catch(() => {});
    }, NEMOTRON_POLL_MS);
    return () => window.clearInterval(timer);
  }, [open, sttEngine, modelsLoading, nemotronState]);

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
        default_preset: profile,
        diarization_enabled_default: diarizationEnabled,
        engine: sttEngine,
      },
      voice_commands: { default_send_mode: sendMode },
      chat: {
        response_detail: detail,
        think,
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

  // Thinking switch: locked when the chosen model can't think, or can't stop thinking.
  const thinkingSupport = models?.llm_thinking?.[llmModel];
  const thinkLocked = thinkingSupport === "always" || thinkingSupport === "none";
  const thinkChecked =
    thinkingSupport === "always" ? true : thinkingSupport === "none" ? false : think;
  const thinkHint =
    thinkingSupport === "always"
      ? "This model always thinks before answering; it can't be turned off."
      : thinkingSupport === "none"
        ? "This model has no thinking mode."
        : think
          ? "On: better answers to harder questions, but slower."
          : "Off: faster answers.";

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
            <Label className="text-sm font-semibold">Transcription</Label>
            <div className="space-y-2">
              <SettingLabel
                text="Engine"
                tooltip="Used for uploads, recordings and voice input (voice commands and voice mode). Nemotron 3.5 Transcribe is an optional second engine and needs its own server."
              />
              <Select value={sttEngine} onValueChange={(v) => setSttEngine(v as SttEngine)}>
                <SelectTrigger aria-label="Transcription engine">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="whisper-pyannote">Whisper + pyannote</SelectItem>
                  <SelectItem value="nemotron">Nemotron 3.5 Transcribe</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {sttEngine === "whisper-pyannote" ? (
              <div className="space-y-2">
                <SettingLabel
                  text="Whisper model"
                  tooltip="Larger models are more accurate but slower."
                />
                <Select value={profile} onValueChange={(v) => setProfile(v as ProcessingProfile)}>
                  <SelectTrigger aria-label="Whisper model">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fast">Fast (small)</SelectItem>
                    <SelectItem value="balanced">Balanced (medium)</SelectItem>
                    <SelectItem value="quality">Quality (large-v3)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  No length limit for recordings and uploads.
                </p>
              </div>
            ) : (
              <div className="space-y-1 rounded-md bg-muted/50 p-2 text-xs">
                <p>
                  <span className="text-muted-foreground">Model: </span>
                  {nemotron?.current || "Nemotron 3.5 Transcribe"}
                </p>
                <p className="text-muted-foreground">
                  Transcribes recordings and uploads up to 60 minutes each. For longer audio,
                  use Whisper.
                </p>
                <p className="text-muted-foreground">
                  Also used for voice input (voice commands and voice mode).
                </p>
                <NemotronServerStatus status={nemotron} loading={modelsLoading} />
              </div>
            )}

            <div className="flex items-center justify-between">
              <SwitchLabel
                htmlFor="diarization-enabled"
                text="Speaker diarization"
                tooltip={
                  sttEngine === "nemotron"
                    ? "Labels who said what. Nemotron detects the speakers itself."
                    : "Labels who said what, with pyannote. Requires a Hugging Face token."
                }
              />
              <Switch
                id="diarization-enabled"
                checked={diarizationEnabled}
                onCheckedChange={setDiarizationEnabled}
              />
            </div>
          </div>

          <div className="space-y-3 rounded-md border p-3">
            <Label className="text-sm font-semibold">Chat</Label>
            <div className="space-y-2">
              <SettingLabel
                text="Model"
                tooltip="The language model used for chat answers and transcript corrections."
              />
              {modelsLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading available models...
                </div>
              ) : models?.llm.reachable === false ? (
                <p className="text-xs text-destructive">
                  Ollama is not reachable. Start Ollama to select a model.
                </p>
              ) : (
                <Select value={llmModel} onValueChange={setLlmModel}>
                  <SelectTrigger aria-label="Chat model">
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

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <SwitchLabel
                  htmlFor="think-enabled"
                  text="Thinking mode"
                  tooltip="The model thinks before it answers typed questions and transcript corrections: better answers to harder questions, but slower. Voice mode never thinks, so it can answer quickly."
                />
                <Switch
                  id="think-enabled"
                  checked={thinkChecked}
                  onCheckedChange={setThink}
                  disabled={thinkLocked}
                />
              </div>
              <p className="text-xs text-muted-foreground">{thinkHint}</p>
            </div>

            <div className="space-y-2">
              <SettingLabel text="Response detail" tooltip="How detailed the AI responses should be." />
              <Select value={detail} onValueChange={(v) => setDetail(v as ResponseDetail)}>
                <SelectTrigger aria-label="Response detail">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="brief">Brief</SelectItem>
                  <SelectItem value="normal">Normal</SelectItem>
                  <SelectItem value="detailed">Detailed</SelectItem>
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

          <div className="space-y-3 rounded-md border p-3">
            <Label className="text-sm font-semibold">Voice</Label>
            <div className="space-y-2">
              <SettingLabel
                text="Voice command default"
                tooltip="Whether to review transcribed voice commands before sending them."
              />
              <Select
                value={sendMode}
                onValueChange={(v) => setSendMode(v as VoiceCommandSendMode)}
              >
                <SelectTrigger aria-label="Voice command default">
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
                text="Voice-mode engine"
                tooltip="Streaming voice mode: Piper speaks German; Kokoro speaks English."
              />
              <Select value={voiceEngine} onValueChange={(v) => setVoiceEngine(v as VoiceEngine)}>
                <SelectTrigger aria-label="Voice-mode engine">
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
                htmlFor="tts-enabled"
                text="TTS enabled"
                tooltip="Enable text-to-speech audio playback of AI responses."
              />
              <Switch id="tts-enabled" checked={ttsEnabled} onCheckedChange={setTtsEnabled} />
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
