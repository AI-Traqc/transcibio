import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActionCard } from "@/components/chat/ActionCard";
import type { ChatActionProposal } from "@/types/chat";

function makeAction(overrides: Partial<ChatActionProposal> = {}): ChatActionProposal {
  return {
    id: "a1",
    action_type: "export_csv",
    title: "Export CSV",
    status: "proposed",
    requires_confirmation: true,
    preview_markdown: "## Preview",
    payload: {},
    created_at_utc: "2026-04-15T12:00:00Z",
    updated_at_utc: "2026-04-15T12:00:00Z",
    executed_at_utc: null,
    error_message: "",
    executions: [],
    artifacts: [],
    ...overrides,
  };
}

describe("ActionCard", () => {
  it("shows Confirm and Cancel buttons for pending proposals", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ActionCard
        action={makeAction()}
        sessionId="s1"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onConfirm).toHaveBeenCalledWith("a1");
    expect(onCancel).toHaveBeenCalledWith("a1");
  });

  it("hides action buttons for non-pending proposals", () => {
    render(
      <ActionCard
        action={makeAction({ status: "completed" })}
        sessionId="s1"
      />,
    );
    expect(screen.queryByRole("button", { name: /confirm/i })).toBeNull();
  });

  it("shows artifact download links when provided", () => {
    render(
      <ActionCard
        action={makeAction({
          status: "completed",
          artifacts: [
            {
              id: "art1",
              file_path: "sessions/s1/exports/out.csv",
              file_name: "out.csv",
              mime_type: "text/csv",
              size_bytes: 128,
              kind: "export_csv",
              created_at_utc: "2026-04-15T12:00:00Z",
              action_proposal_id: "a1",
              session_id: "s1",
            },
          ],
        })}
        sessionId="s1"
      />,
    );
    const link = screen.getByRole("link", { name: /out\.csv/ });
    expect(link).toHaveAttribute("href", "/api/v1/sessions/s1/artifacts/art1");
  });
});
