import { useCallback, useEffect, useRef, useState } from "react";
import { MicVAD, utils } from "@ricky0123/vad-web";
import * as voiceApi from "@/api/voice";
import { useVoiceTurn } from "@/hooks/useVoiceTurn";
import type { VoiceEngine } from "@/types/settings";

export type ConversationPhase =
  | "off"
  | "starting"
  | "listening"
  | "transcribing"
  | "speaking";

export interface VadConversationConfig {
  sessionId: string;
  engine: VoiceEngine;
  transcriptRevisionId: string | null;
  onTurnComplete?: () => void;
}

export interface UseVadConversationResult {
  phase: ConversationPhase;
  streamingText: string;
  error: string | null;
  start: (config: VadConversationConfig) => Promise<void>;
  stop: () => void;
}

// VAD assets are bundled locally (see frontend/scripts/copy-vad-assets.mjs) so
// voice mode works offline — no CDN fetch.
const VAD_ASSET_PATH = "/vad/";

/**
 * Continuous hands-free conversation loop with barge-in.
 *
 * A browser VAD (Silero) listens the whole time voice mode is on. When you stop
 * talking it transcribes the utterance (STT), then streams a spoken answer via
 * `useVoiceTurn`, then listens again — no per-turn button. If you start talking
 * while the assistant speaks, playback is cut (barge-in) and your new turn is
 * captured.
 */
export function useVadConversation(): UseVadConversationResult {
  const { start: startTurn, stop: stopTurn, text, error: turnError } = useVoiceTurn();
  const [phase, setPhase] = useState<ConversationPhase>("off");
  const [error, setError] = useState<string | null>(null);

  const vadRef = useRef<MicVAD | null>(null);
  const configRef = useRef<VadConversationConfig | null>(null);
  const phaseRef = useRef<ConversationPhase>("off");
  const activeRef = useRef(false); // true while voice mode is engaged

  const setPhaseBoth = useCallback((next: ConversationPhase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  const handleSpeechEnd = useCallback(
    async (audio: Float32Array) => {
      const config = configRef.current;
      if (!config || !activeRef.current) return;
      try {
        setPhaseBoth("transcribing");
        const wav = utils.encodeWAV(audio);
        const blob = new Blob([wav], { type: "audio/wav" });
        // The selected TTS engine fixes the conversation language (Piper=de, Kokoro=en).
        // Pin STT to it too: otherwise faster-whisper auto-detects per short clip and
        // mis-detects German as e.g. Arabic, producing garbage that wrecks the answer.
        const languageHint = config.engine === "kokoro" ? "en" : "de";
        const resp = await voiceApi.sendVoiceCommand(config.sessionId, blob, "voice.wav", {
          sendMode: "review_then_send",
          languageHint,
        });
        if (!activeRef.current) return;
        const said = (resp.transcribed_text || "").trim();
        // `transcription_empty` means STT heard no speech (a VAD false-trigger on
        // noise/silence) and `said` is a placeholder, not a real utterance — keep
        // listening instead of sending the placeholder to the assistant.
        if (!said || resp.transcription_empty) {
          setPhaseBoth("listening");
          return;
        }
        setPhaseBoth("speaking");
        startTurn({
          sessionId: config.sessionId,
          text: said,
          engine: config.engine,
          transcriptRevisionId: config.transcriptRevisionId,
          onDone: () => {
            config.onTurnComplete?.();
            if (activeRef.current) setPhaseBoth("listening");
          },
        });
      } catch {
        setError("Spracherkennung fehlgeschlagen.");
        if (activeRef.current) setPhaseBoth("listening");
      }
    },
    [setPhaseBoth, startTurn],
  );

  const handleSpeechStart = useCallback(() => {
    if (!activeRef.current) return;
    // Barge-in: cut the assistant off the moment the user starts talking.
    if (phaseRef.current === "speaking") stopTurn();
    setPhaseBoth("listening");
  }, [setPhaseBoth, stopTurn]);

  const start = useCallback(
    async (config: VadConversationConfig) => {
      configRef.current = config;
      activeRef.current = true;
      setError(null);
      if (vadRef.current) {
        vadRef.current.start();
        setPhaseBoth("listening");
        return;
      }
      setPhaseBoth("starting");
      try {
        const vad = await MicVAD.new({
          // Worklet + Silero model are fetched, so a root-relative path is fine.
          baseAssetPath: VAD_ASSET_PATH,
          // ONNX Runtime loads its wasm via dynamic import(); Vite blocks importing
          // /public paths as modules, so use an absolute URL it treats as external.
          onnxWASMBasePath: `${window.location.origin}${VAD_ASSET_PATH}`,
          onSpeechStart: handleSpeechStart,
          onSpeechEnd: handleSpeechEnd,
        });
        vadRef.current = vad;
        vad.start();
        setPhaseBoth("listening");
      } catch (e) {
        // Surface the real cause (asset 404, mic permission, etc.) for debugging.
        console.error("[voice] VAD start failed", e);
        activeRef.current = false;
        setError("Mikrofonzugriff fehlgeschlagen oder Sprachmodus konnte nicht starten.");
        setPhaseBoth("off");
      }
    },
    [handleSpeechStart, handleSpeechEnd, setPhaseBoth],
  );

  const stop = useCallback(() => {
    activeRef.current = false;
    vadRef.current?.pause();
    stopTurn();
    setPhaseBoth("off");
  }, [setPhaseBoth, stopTurn]);

  useEffect(
    () => () => {
      vadRef.current?.destroy();
      vadRef.current = null;
    },
    [],
  );

  return { phase, streamingText: text, error: error ?? turnError, start, stop };
}
