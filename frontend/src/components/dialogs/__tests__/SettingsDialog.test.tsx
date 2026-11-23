import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SettingsDialog } from "@/components/dialogs/SettingsDialog";
import type {
  ModelsResponse,
  NemotronStatus,
  SettingsPayload,
  SttEngine,
} from "@/types/settings";

const getAvailableModels = vi.fn<() => Promise<ModelsResponse>>();
const getNemotronStatus = vi.fn<() => Promise<NemotronStatus>>();
vi.mock("@/api/settings", () => ({
  getAvailableModels: () => getAvailableModels(),
  getNemotronStatus: () => getNemotronStatus(),
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

const provider = (name: string) => ({
  provider: name,
  current: "",
  available: [],
  reachable: true,
  error: "",
});

function makeNemotron(
  state: NemotronStatus["state"],
  startingSeconds: number | null = null,
): NemotronStatus {
  return {
    ...provider("nemotron"),
    current: "nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-NVFP4",
    reachable: state === "running",
    state,
    starting_seconds: startingSeconds,
  };
}

function makeModels(
  current: string,
  thinking: ModelsResponse["llm_thinking"],
  nemotron: NemotronStatus = makeNemotron("stopped"),
): ModelsResponse {
  return {
    stt: provider("faster-whisper"),
    llm: { ...provider("ollama"), current, available: [current] },
    diarization: provider("pyannote"),
    nemotron,
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
  beforeEach(() => {
    getAvailableModels.mockReset();
    getNemotronStatus.mockReset();
  });
  afterEach(() => vi.useRealTimers());

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

  it("shows that the Nemotron server is still loading, with the elapsed time", async () => {
    getAvailableModels.mockResolvedValue(
      makeModels("gemma4:26b", {}, makeNemotron("starting", 125)),
    );
    renderDialog(makeSettings("nemotron"));
    expect(await screen.findByText(/loading the model and warming up \(2:05\)/)).toBeTruthy();
    expect(screen.queryByText(/Server is not running/)).toBeNull();
  });

  it("refreshes the Nemotron status until the server is running", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    getAvailableModels.mockResolvedValue(
      makeModels("gemma4:26b", {}, makeNemotron("starting", 10)),
    );
    getNemotronStatus
      .mockResolvedValueOnce(makeNemotron("starting", 15))
      .mockResolvedValue(makeNemotron("running"));
    renderDialog(makeSettings("nemotron"));
    await screen.findByText(/\(0:10\)/);

    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(await screen.findByText(/\(0:15\)/)).toBeTruthy();

    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(await screen.findByText("Server is running.")).toBeTruthy();

    // Running: no more polling.
    await act(() => vi.advanceTimersByTimeAsync(20000));
    expect(getNemotronStatus).toHaveBeenCalledTimes(2);
  });

  it("doesn't poll the Nemotron status for the Whisper engine", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    getAvailableModels.mockResolvedValue(makeModels("gemma4:26b", {}));
    renderDialog(makeSettings("whisper-pyannote"));
    await screen.findByLabelText("Whisper model");
    await act(() => vi.advanceTimersByTimeAsync(20000));
    expect(getNemotronStatus).not.toHaveBeenCalled();
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
