import { useCallback, useEffect, useRef, useState } from "react";
import { PcmStreamPlayer } from "@/audio/PcmStreamPlayer";
import type { VoiceEngine } from "@/types/settings";

export type VoiceTurnStatus = "idle" | "connecting" | "speaking" | "error";

// Engines emit at a fixed native rate; the AudioContext is created at that rate
// inside the user gesture so browser autoplay policy allows playback.
const ENGINE_SAMPLE_RATE: Record<VoiceEngine, number> = {
  piper: 22050,
  kokoro: 24000,
};

export interface StartVoiceTurnArgs {
  sessionId: string;
  text: string;
  engine: VoiceEngine;
  transcriptRevisionId?: string | null;
  onDone?: (assistantMessageId: string) => void;
}

export interface UseVoiceTurnResult {
  status: VoiceTurnStatus;
  text: string;
  error: string | null;
  start: (args: StartVoiceTurnArgs) => void;
  stop: () => void;
}

export function useVoiceTurn(): UseVoiceTurnResult {
  const [status, setStatus] = useState<VoiceTurnStatus>("idle");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const playerRef = useRef<PcmStreamPlayer | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  const teardown = useCallback(() => {
    socketRef.current?.close();
    socketRef.current = null;
    playerRef.current?.stop();
  }, []);

  // One AudioContext is reused across turns. Creating a fresh PcmStreamPlayer per
  // turn would leak an AudioContext each time (browsers cap active contexts at ~6),
  // so a long hands-free conversation would eventually fail to play.
  const ensurePlayer = useCallback((engine: VoiceEngine): PcmStreamPlayer => {
    const existing = playerRef.current;
    if (existing) {
      existing.setSampleRate(ENGINE_SAMPLE_RATE[engine]);
      return existing;
    }
    const player = new PcmStreamPlayer(ENGINE_SAMPLE_RATE[engine]);
    playerRef.current = player;
    return player;
  }, []);

  // Close the WebSocket and AudioContext when the hook unmounts (e.g. session
  // switch mid-turn) so neither leaks.
  useEffect(
    () => () => {
      socketRef.current?.close();
      socketRef.current = null;
      void playerRef.current?.close();
      playerRef.current = null;
    },
    [],
  );

  const stop = useCallback(() => {
    teardown();
    setStatus("idle");
  }, [teardown]);

  const start = useCallback(
    (args: StartVoiceTurnArgs) => {
      teardown(); // barge-in: cancel any in-flight turn

      const player = ensurePlayer(args.engine);
      player.stop(); // flush any audio still scheduled from a previous turn
      setStatus("connecting");
      setText("");
      setError(null);

      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${window.location.host}/api/v1/voice-turn`);
      ws.binaryType = "arraybuffer";
      socketRef.current = ws;

      ws.onopen = () =>
        ws.send(
          JSON.stringify({
            session_id: args.sessionId,
            text: args.text,
            engine: args.engine,
            transcript_revision_id: args.transcriptRevisionId ?? undefined,
          }),
        );

      ws.onmessage = (event) => {
        if (typeof event.data === "string") {
          const msg = JSON.parse(event.data) as Record<string, unknown>;
          if (msg.type === "start") {
            playerRef.current?.setSampleRate(Number(msg.sample_rate));
            setStatus("speaking");
          } else if (msg.type === "sentence") {
            setText((prev) => `${prev} ${String(msg.text)}`.trim());
          } else if (msg.type === "done") {
            setStatus("idle");
            args.onDone?.(String(msg.assistant_message_id ?? ""));
          } else if (msg.type === "error") {
            setStatus("error");
            setError(String(msg.message));
          }
          return;
        }
        playerRef.current?.enqueue(event.data as ArrayBuffer);
      };

      ws.onerror = () => {
        setStatus("error");
        setError("Verbindung zum Sprachmodus fehlgeschlagen.");
      };
    },
    [teardown, ensurePlayer],
  );

  return { status, text, error, start, stop };
}
