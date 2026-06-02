import type { JobEventEnvelope } from "@/types/job";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") return payload.detail;
    return `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = path.startsWith("/") ? path : `${API_BASE}/${path}`;
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function apiFetchJson<T>(
  path: string,
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  body?: unknown,
): Promise<T> {
  const init: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }
  return apiFetch<T>(path, init);
}

export async function apiFetchEmpty(
  path: string,
  method: "POST" | "DELETE",
): Promise<void> {
  await apiFetch<void>(path, { method });
}

export async function apiForm<T>(
  path: string,
  form: FormData,
  method: "POST" | "PUT" = "POST",
): Promise<T> {
  return apiFetch<T>(path, { method, body: form });
}

export type JobEventHandlers = {
  onSnapshot?: (event: JobEventEnvelope) => void;
  onQueued?: (event: JobEventEnvelope) => void;
  onStarted?: (event: JobEventEnvelope) => void;
  onProgress?: (event: JobEventEnvelope) => void;
  onStage?: (event: JobEventEnvelope) => void;
  onSucceeded?: (event: JobEventEnvelope) => void;
  onFailed?: (event: JobEventEnvelope) => void;
  onKeepalive?: (event: JobEventEnvelope) => void;
  onAny?: (event: JobEventEnvelope) => void;
  onError?: (err: unknown) => void;
};

export type JobEventStream = {
  close: () => void;
};

const HANDLER_BY_TYPE: Record<
  string,
  keyof Pick<
    JobEventHandlers,
    | "onSnapshot"
    | "onQueued"
    | "onStarted"
    | "onProgress"
    | "onSucceeded"
    | "onFailed"
    | "onKeepalive"
  >
> = {
  "job.snapshot": "onSnapshot",
  "job.queued": "onQueued",
  "job.started": "onStarted",
  "job.progress": "onProgress",
  "job.succeeded": "onSucceeded",
  "job.failed": "onFailed",
  keepalive: "onKeepalive",
};

export function connectJobEvents(
  jobId: string,
  handlers: JobEventHandlers,
): JobEventStream {
  const url = `${API_BASE}/events/jobs/${jobId}`;
  const source = new EventSource(url);
  let closed = false;

  const closeStream = () => {
    if (closed) return;
    closed = true;
    for (const [type, listener] of listeners) {
      source.removeEventListener(type, listener as EventListener);
    }
    source.onmessage = null;
    source.onerror = null;
    source.close();
  };

  const dispatch = (rawData: string) => {
    if (closed) return;
    try {
      const envelope = JSON.parse(rawData) as JobEventEnvelope;
      const key = HANDLER_BY_TYPE[envelope.type];
      if (key) {
        handlers[key]?.(envelope);
      } else if (envelope.type.startsWith("transcription.") || envelope.type.startsWith("chat.")) {
        handlers.onStage?.(envelope);
      }
      handlers.onAny?.(envelope);
      // Terminal events: close immediately so EventSource does not auto-reconnect
      // after the server closes the stream.
      if (envelope.type === "job.succeeded" || envelope.type === "job.failed") {
        closeStream();
      }
    } catch (err) {
      handlers.onError?.(err);
    }
  };

  const listenedTypes = [
    "job.snapshot",
    "job.queued",
    "job.started",
    "job.progress",
    "job.succeeded",
    "job.failed",
    "keepalive",
    // Stage events from orchestrators — forwarded to onStage/onAny.
    "transcription.stage",
    "transcription.started",
    "transcription.completed",
    "chat.retrieval.started",
    "chat.retrieval.completed",
    "chat.llm.started",
    "chat.llm.completed",
    "chat.citations.ready",
    "chat.action_proposals.ready",
    "chat.assistant.completed",
  ];

  const listeners: Array<[string, (e: MessageEvent) => void]> = [];
  for (const type of listenedTypes) {
    const listener = (event: MessageEvent) => dispatch(event.data);
    source.addEventListener(type, listener as EventListener);
    listeners.push([type, listener]);
  }

  // Default unnamed events fall through `onmessage`.
  source.onmessage = (event) => dispatch(event.data);
  source.onerror = (err) => {
    if (closed) return;
    // If the server closed the stream cleanly after a terminal event, the
    // browser will fire an error here and then attempt to reconnect. When
    // readyState === CLOSED, there's nothing to recover; stop the reconnect
    // loop by tearing down the source.
    if (source.readyState === EventSource.CLOSED) {
      closeStream();
      return;
    }
    handlers.onError?.(err);
  };

  return {
    close: closeStream,
  };
}

export function artifactDownloadUrl(
  sessionId: string,
  artifactId: string,
): string {
  return `${API_BASE}/sessions/${sessionId}/artifacts/${artifactId}`;
}

export function ttsAudioUrl(sessionId: string, messageId: string): string {
  return `${API_BASE}/sessions/${sessionId}/tts/${messageId}/audio`;
}

export function sessionAudioUrl(
  sessionId: string,
  audioAssetId: string,
): string {
  return `${API_BASE}/sessions/${sessionId}/audio/${audioAssetId}/stream`;
}
