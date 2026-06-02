import { apiForm } from "./client";
import type {
  VoiceCommandResponse,
  VoiceCommandSendMode,
} from "@/types/voice";

export function sendVoiceCommand(
  sessionId: string,
  blob: Blob,
  fileName: string,
  options: {
    sendMode?: VoiceCommandSendMode;
    languageHint?: "auto" | "en" | "de";
    transcriptRevisionId?: string | null;
  } = {},
): Promise<VoiceCommandResponse> {
  const form = new FormData();
  form.append("audio_file", blob, fileName);
  if (options.sendMode) {
    form.append("send_mode", options.sendMode);
  }
  if (options.languageHint) {
    form.append("language_hint", options.languageHint);
  }
  if (options.transcriptRevisionId !== undefined &&
      options.transcriptRevisionId !== null) {
    form.append("transcript_revision_id", options.transcriptRevisionId);
  }
  return apiForm<VoiceCommandResponse>(
    `/api/v1/sessions/${sessionId}/voice-commands`,
    form,
  );
}
