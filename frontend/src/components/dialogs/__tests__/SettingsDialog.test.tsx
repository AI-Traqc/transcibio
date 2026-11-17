import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SettingsDialog } from "@/components/dialogs/SettingsDialog";
import type { ModelsResponse, SettingsPayload, SttEngine } from "@/types/settings";

const getAvailableModels = vi.fn<() => Promise<ModelsResponse>>();
vi.mock("@/api/settings", () => ({
  getAvailableModels: () => getAvailableModels(),
}));

function makeSettings(engine: SttEngine, think = false): SettingsPayload {
  return {
    processing_profile: "balanced",
    stt: {
      default_language_hint: "auto",
      default_preset: "balanced",
      diarization_enabled_default: true,
      engine,
    },
    chat: { llm_provider: "ollama", model_name: "", response_detail: "normal", think },
    voice_commands: { default_send_mode: "review_then_send" },
    tts: {
      enabled: false,
      auto_generate_on_chat_reply: false,
      auto_play: false,
      provider: "piper",
      voice: "",
      speed: 1,
      voice_engine: "piper",
    },
    ui: { show_timestamps_in_citations: true },
  };
}

function makeModels(current: string, thinking: ModelsResponse["llm_thinking"]): ModelsResponse {
  const provider = (name: string) => ({
    provider: name,
    current: "",
    available: [],
    reachable: true,
    error: "",
  });
  return {
    stt: provider("faster-whisper"),
    llm: { ...provider("ollama"), current, available: [current] },
    diarization: provider("pyannote"),
    nemotron: {
      ...provider("nemotron"),
      current: "nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-NVFP4",
      reachable: false,
    },
    llm_thinking: thinking,
  };
}

function renderDialog(settings: SettingsPayload) {
  return render(
    <TooltipProvider>
      <SettingsDialog
        open
        settings={settings}
        busy={false}
        error={null}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
        onDeleteAllSessions={vi.fn()}
      />
    </TooltipProvider>,
  );
}

describe("SettingsDialog", () => {
  beforeEach(() => getAvailableModels.mockReset());

  it("shows the Whisper model choice only for the Whisper engine", async () => {
    getAvailableModels.mockResolvedValue(makeModels("gemma4:26b", { "gemma4:26b": "optional" }));
    renderDialog(makeSettings("whisper-pyannote"));
    expect(await screen.findByLabelText("Whisper model")).toBeTruthy();
  });

  it("hides the Whisper model choice for Nemotron and shows its server status", async () => {
    getAvailableModels.mockResolvedValue(makeModels("gemma4:26b", { "gemma4:26b": "optional" }));
    renderDialog(makeSettings("nemotron"));
    expect(await screen.findByText(/Server is not running/)).toBeTruthy();
    expect(screen.queryByLabelText("Whisper model")).toBeNull();
    expect(screen.getByText(/NVFP4/)).toBeTruthy();
  });

  it("lets the thinking switch be changed for models that support it", async () => {
    getAvailableModels.mockResolvedValue(makeModels("gemma4:26b", { "gemma4:26b": "optional" }));
    renderDialog(makeSettings("whisper-pyannote", true));
    await screen.findByText(/better answers to harder questions/);
    const toggle = screen.getByRole("switch", { name: /thinking mode/i });
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    expect((toggle as HTMLButtonElement).disabled).toBe(false);
  });

  it("locks the thinking switch off for models without thinking", async () => {
    getAvailableModels.mockResolvedValue(makeModels("granite4:3b", { "granite4:3b": "none" }));
    renderDialog(makeSettings("whisper-pyannote", true));
    await screen.findByText("This model has no thinking mode.");
    const toggle = screen.getByRole("switch", { name: /thinking mode/i });
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    expect((toggle as HTMLButtonElement).disabled).toBe(true);
  });

  it("locks the thinking switch on for models that always think", async () => {
    getAvailableModels.mockResolvedValue(makeModels("gpt-oss:120b", { "gpt-oss:120b": "always" }));
    renderDialog(makeSettings("whisper-pyannote", false));
    await waitFor(() => screen.getByText(/always thinks before answering/));
    const toggle = screen.getByRole("switch", { name: /thinking mode/i });
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    expect((toggle as HTMLButtonElement).disabled).toBe(true);
  });
});
