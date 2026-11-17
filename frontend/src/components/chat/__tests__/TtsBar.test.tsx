import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TtsBar } from "@/components/chat/TtsBar";
import type { TtsStatusResponse } from "@/types/tts";

function status(value: string): TtsStatusResponse {
  return {
    message_id: "m1",
    status: value,
    audio_asset_id: "a1",
    mime_type: "audio/wav",
    duration_ms: 1000,
    error_message: "",
    download_url: "/api/v1/sessions/s1/tts/m1/audio",
    model_name: "piper",
  };
}

describe("TtsBar", () => {
  it("shows the Play button until audio exists", () => {
    const onGenerate = vi.fn();
    render(
      <TtsBar messageId="m1" status={undefined} busy={false} onGenerate={onGenerate} audioUrl="/a" />,
    );
    fireEvent.click(screen.getByRole("button", { name: /play/i }));
    expect(onGenerate).toHaveBeenCalled();
  });

  it("shows the audio player when the backend reports succeeded", () => {
    render(
      <TtsBar messageId="m1" status={status("succeeded")} busy={false} onGenerate={vi.fn()} audioUrl="/a" />,
    );
    expect(screen.getByLabelText("Answer audio")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /play/i })).toBeNull();
  });
});
