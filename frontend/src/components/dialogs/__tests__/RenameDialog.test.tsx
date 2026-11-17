import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RenameDialog } from "@/components/dialogs/RenameDialog";
import type { SessionRecord } from "@/types/session";

function makeSession(): SessionRecord {
  return {
    id: "s1",
    created_at_utc: "2026-04-15T12:00:00Z",
    updated_at_utc: "2026-04-15T12:00:00Z",
    title: "Original title",
    source_kind: "upload",
    source_name: "",
    source_language_hint: "auto",
    command_language_hint: "auto",
    status: "idle",
    last_error: "",
    active_transcript_revision_id: null,
  };
}

describe("RenameDialog", () => {
  it("prefills the session title and emits on confirm", () => {
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <RenameDialog
        open
        session={makeSession()}
        busy={false}
        error={null}
        onOpenChange={onOpenChange}
        onConfirm={onConfirm}
      />,
    );
    const input = screen.getByRole("textbox");
    expect((input as HTMLInputElement).value).toBe("Original title");
    fireEvent.change(input, { target: { value: "Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onConfirm).toHaveBeenCalledWith("Renamed");
  });

  it("disables Save when the title is empty", () => {
    render(
      <RenameDialog
        open
        session={makeSession()}
        busy={false}
        error={null}
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "   " } });
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
  });

  it("renders an error message when provided", () => {
    render(
      <RenameDialog
        open
        session={makeSession()}
        busy={false}
        error="Boom"
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByText("Boom")).toBeInTheDocument();
  });
});
