import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageBubble } from "@/components/chat/MessageBubble";
import type { ChatMessage } from "@/types/chat";

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "m1",
    thread_id: "t1",
    session_id: "s1",
    transcript_revision_id: null,
    role: "assistant",
    content_markdown: "Hello from the assistant.",
    content_plain_text: "Hello from the assistant.",
    source_kind: "assistant_reply",
    status: "completed",
    model_name: "ollama:llama3",
    created_at_utc: "2026-04-15T12:00:00Z",
    metadata: {},
    citations: [],
    action_proposals: [],
    ...overrides,
  };
}

describe("MessageBubble", () => {
  it("renders assistant message content", () => {
    render(
      <MessageBubble
        message={makeMessage()}
        sessionId="s1"
        settings={null}
        ttsStatus={undefined}
        ttsBusy={false}
        ttsAudioUrl=""
      />,
    );
    expect(screen.getByText("Hello from the assistant.")).toBeInTheDocument();
    expect(screen.getByText("Assistant")).toBeInTheDocument();
  });

  it("renders user message with user label", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "user", content_markdown: "hi" })}
        sessionId="s1"
        settings={null}
        ttsStatus={undefined}
        ttsBusy={false}
        ttsAudioUrl=""
      />,
    );
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("hi")).toBeInTheDocument();
  });

  it("shows 'Generating response…' for an empty queued assistant message", () => {
    render(
      <MessageBubble
        message={makeMessage({
          content_markdown: "",
          content_plain_text: "",
          status: "queued",
        })}
        sessionId="s1"
        settings={null}
        ttsStatus={undefined}
        ttsBusy={false}
        ttsAudioUrl=""
      />,
    );
    expect(screen.getByText(/generating response/i)).toBeInTheDocument();
  });
});
