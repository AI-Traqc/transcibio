import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SessionItem } from "@/components/sidebar/SessionItem";
import type { SessionRecord } from "@/types/session";

function makeSession(overrides: Partial<SessionRecord> = {}): SessionRecord {
  return {
    id: "s1",
    created_at_utc: "2026-04-15T12:00:00Z",
    updated_at_utc: "2026-04-15T12:00:00Z",
    title: "Sprint review",
    source_kind: "upload",
    source_name: "",
    source_language_hint: "auto",
    command_language_hint: "auto",
    status: "idle",
    last_error: "",
    active_transcript_revision_id: null,
    ...overrides,
  };
}

describe("SessionItem", () => {
  it("calls onSelect when the title is clicked", () => {
    const onSelect = vi.fn();
    render(
      <SessionItem
        session={makeSession()}
        selected={false}
        onSelect={onSelect}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Sprint review"));
    expect(onSelect).toHaveBeenCalled();
  });

  it("renders 'Untitled' when the title is empty", () => {
    render(
      <SessionItem
        session={makeSession({ title: "" })}
        selected={false}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText("Untitled")).toBeInTheDocument();
  });
});
