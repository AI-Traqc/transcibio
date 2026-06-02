import { expect, test } from "@playwright/test";

type SessionRecord = {
  id: string;
  title: string;
  source_kind: string;
  source_name: string;
  source_language_hint: string;
  command_language_hint: string;
  status: string;
  last_error: string;
  active_transcript_revision_id: string | null;
  created_at_utc: string;
  updated_at_utc: string;
};

const FIXED_NOW = "2026-04-15T12:00:00.000Z";

function jsonResponse(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

function emptyResponse(status = 204) {
  return { status, body: "" };
}

test("sidebar creates, renames, and deletes sessions against the new shell", async ({
  page,
}) => {
  let counter = 0;
  const sessions = new Map<string, SessionRecord>();

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/api/v1/settings" && method === "GET") {
      return route.fulfill(
        jsonResponse({
          processing_profile: "balanced",
          stt: {
            default_language_hint: "auto",
            default_preset: "balanced",
            diarization_enabled_default: true,
          },
          chat: {
            llm_provider: "ollama",
            model_name: "llama3",
            response_detail: "normal",
          },
          voice_commands: { default_send_mode: "review_then_send" },
          tts: {
            enabled: false,
            auto_generate_on_chat_reply: false,
            auto_play: false,
            provider: "piper",
            voice: "",
            speed: 1,
          },
          ui: { show_timestamps_in_citations: false },
        }),
      );
    }

    if (path === "/api/v1/sessions" && method === "GET") {
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const list = Array.from(sessions.values()).filter((s) =>
        q ? s.title.toLowerCase().includes(q) : true,
      );
      return route.fulfill(jsonResponse(list));
    }

    if (path === "/api/v1/sessions" && method === "POST") {
      counter += 1;
      const body = (request.postDataJSON() ?? {}) as { title?: string };
      const record: SessionRecord = {
        id: `s-${counter}`,
        title: body.title ?? "New session",
        source_kind: "upload",
        source_name: "",
        source_language_hint: "auto",
        command_language_hint: "auto",
        status: "idle",
        last_error: "",
        active_transcript_revision_id: null,
        created_at_utc: FIXED_NOW,
        updated_at_utc: FIXED_NOW,
      };
      sessions.set(record.id, record);
      return route.fulfill(jsonResponse(record));
    }

    const sessionMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)$/);
    if (sessionMatch && method === "PATCH") {
      const id = sessionMatch[1];
      const record = sessions.get(id);
      if (!record) return route.fulfill(jsonResponse({ detail: "Not found" }, 404));
      const body = request.postDataJSON() as { title?: string };
      const updated: SessionRecord = {
        ...record,
        title: body.title ?? record.title,
        updated_at_utc: FIXED_NOW,
      };
      sessions.set(id, updated);
      return route.fulfill(jsonResponse(updated));
    }

    if (sessionMatch && method === "DELETE") {
      const id = sessionMatch[1];
      if (!sessions.delete(id)) {
        return route.fulfill(jsonResponse({ detail: "Not found" }, 404));
      }
      return route.fulfill(emptyResponse(204));
    }

    if (sessionMatch && method === "GET") {
      const id = sessionMatch[1];
      const record = sessions.get(id);
      if (!record) return route.fulfill(jsonResponse({ detail: "Not found" }, 404));
      return route.fulfill(jsonResponse(record));
    }

    // Chat + transcript endpoints: empty bodies are fine for this smoke test.
    if (path.endsWith("/chat") && method === "GET") {
      return route.fulfill(
        jsonResponse({ session_id: "s-1", thread: null, messages: [] }),
      );
    }
    if (path.endsWith("/transcript") && method === "GET") {
      return route.fulfill(jsonResponse({ detail: "No transcript" }, 404));
    }
    if (path.endsWith("/transcript/revisions") && method === "GET") {
      return route.fulfill(jsonResponse([]));
    }

    return route.fulfill(jsonResponse({ detail: "unmocked" }, 404));
  });

  await page.goto("/");

  await expect(page.getByRole("heading", { name: /start a new session/i })).toBeVisible();

  await page.getByRole("button", { name: /new session/i }).first().click();

  const sessionRow = page.getByText("New session").last();
  await expect(sessionRow).toBeVisible();

  await page.getByRole("button", { name: "More" }).first().click();
  await page.getByRole("menuitem", { name: /rename/i }).click();

  const dialogInput = page.getByRole("textbox");
  await dialogInput.fill("Redesign kickoff");
  await page.getByRole("button", { name: /^save$/i }).click();

  await expect(page.getByRole("heading", { name: "Redesign kickoff" })).toBeVisible();

  await page.getByRole("button", { name: "More" }).first().click();
  await page.getByRole("menuitem", { name: /delete/i }).click();
  await page.getByRole("button", { name: /^delete$/i }).click();

  await expect(page.getByRole("heading", { name: /start a new session/i })).toBeVisible();
});
