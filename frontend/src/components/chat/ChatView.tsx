import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { ChatThread } from "@/components/chat/ChatThread";
import { EmptyState } from "@/components/chat/EmptyState";
import { VoiceModeBar } from "@/components/chat/VoiceModeBar";
import { VoiceReviewBanner } from "@/components/chat/VoiceReviewBanner";
import { Composer } from "@/components/composer/Composer";
import { SessionDrawer } from "@/components/drawers/SessionDrawer";
import { TranscriptDrawer } from "@/components/drawers/TranscriptDrawer";
import { useAudio } from "@/hooks/useAudio";
import { useChat } from "@/hooks/useChat";
import { useDisclosure } from "@/hooks/useDisclosure";
import { useJobEvents } from "@/hooks/useJobEvents";
import { useTranscript } from "@/hooks/useTranscript";
import { useTts } from "@/hooks/useTts";
import { useVadConversation } from "@/hooks/useVadConversation";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { sessionAudioUrl } from "@/api/client";
import * as actionsApi from "@/api/actions";
import * as voiceApi from "@/api/voice";
import type { JobUiState } from "@/types/job";
import type { SessionRecord } from "@/types/session";
import type { SettingsPayload } from "@/types/settings";

const INITIAL_JOB: JobUiState = {
  jobId: "",
  status: "idle",
  progress: 0,
  events: [],
  errorMessage: "",
  output: null,
};

interface ChatViewProps {
  session: SessionRecord | null;
  settings: SettingsPayload | null;
  onNewSession: () => void;
  onSessionsRefresh?: () => void;
}

export function ChatView({ session, settings, onNewSession, onSessionsRefresh }: ChatViewProps) {
  const sessionId = session?.id ?? null;
  const chat = useChat(sessionId);
  const transcript = useTranscript(sessionId);
  const audio = useAudio(sessionId);
  const tts = useTts(sessionId);
  const jobs = useJobEvents();
  const commandRecorder = useVoiceRecorder("command", sessionId);
  const meetingRecorder = useVoiceRecorder("meeting", sessionId);
  const conversation = useVadConversation();

  const sessionDrawer = useDisclosure(false, sessionId);
  const transcriptDrawer = useDisclosure(false, sessionId);

  const [transcriptionJob, setTranscriptionJob] = useState<JobUiState | null>(null);
  const [chatJob, setChatJob] = useState<JobUiState | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [voiceReviewActive, setVoiceReviewActive] = useState(false);
  const [voiceModeEnabled, setVoiceModeEnabled] = useState(false);
  const composerSubmitPendingRef = useRef<boolean>(false);

  useEffect(() => {
    setTranscriptionJob(null);
    setChatJob(null);
    setActionBusy(false);
    setVoiceReviewActive(false);
    setVoiceModeEnabled(false);
    conversation.stop();
    jobs.detachAll();
    audio.reset();
    composerSubmitPendingRef.current = false;
    if (!sessionId) return;
    chat.reload();
    transcript.load();
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const attachChatJob = (jobId: string) => {
    jobs.detach(jobId);
    setChatJob({ ...INITIAL_JOB, jobId, status: "queued", startedAt: Date.now() });
    jobs.attach(
      jobId,
      "chat",
      {
        onProgress: (e) => {
          const p = (e.payload as { progress?: number }).progress;
          setChatJob((prev) =>
            prev && prev.jobId === jobId
              ? { ...prev, status: "running", progress: typeof p === "number" ? p : prev.progress }
              : prev,
          );
        },
        onStage: (e) => {
          const payload = e.payload as { progress?: number; message?: string };
          setChatJob((prev) =>
            prev && prev.jobId === jobId
              ? {
                  ...prev,
                  status: "running",
                  stage: e.type,
                  stageMessage: payload.message,
                  progress:
                    typeof payload.progress === "number"
                      ? payload.progress
                      : prev.progress,
                }
              : prev,
          );
        },
        onSucceeded: () => {
          chat.reload();
          setChatJob((prev) => (prev && prev.jobId === jobId ? null : prev));
        },
        onFailed: (e) => {
          const msg =
            (e.payload as { error_message?: string }).error_message ??
            "Reply failed";
          toast.error(msg);
          setChatJob((prev) => (prev && prev.jobId === jobId ? null : prev));
          chat.reload();
        },
      },
      sessionId,
    );
  };

  const attachTranscriptionJob = (jobId: string) => {
    setTranscriptionJob({
      ...INITIAL_JOB,
      jobId,
      status: "queued",
      startedAt: Date.now(),
    });
    jobs.attach(
      jobId,
      "transcription",
      {
        onProgress: (e) => {
          const p = (e.payload as { progress?: number }).progress;
          setTranscriptionJob((prev) =>
            prev && prev.jobId === jobId
              ? { ...prev, status: "running", progress: typeof p === "number" ? p : prev.progress }
              : prev,
          );
        },
        onStage: (e) => {
          const payload = e.payload as {
            stage?: string;
            progress?: number;
            message?: string;
          };
          setTranscriptionJob((prev) =>
            prev && prev.jobId === jobId
              ? {
                  ...prev,
                  status: "running",
                  stage: payload.stage ?? prev.stage,
                  stageMessage: payload.message,
                  progress:
                    typeof payload.progress === "number"
                      ? payload.progress
                      : prev.progress,
                }
              : prev,
          );
        },
        onSucceeded: () => {
          setTranscriptionJob(null);
          transcript.load();
          toast.success("Transcript ready");
          onSessionsRefresh?.();
        },
        onFailed: (e) => {
          const msg =
            (e.payload as { error_message?: string }).error_message ??
            "Transcription failed";
          toast.error(msg);
          setTranscriptionJob(null);
        },
      },
      sessionId,
    );
  };

  const submit = async (override?: string) => {
    const text = (override ?? chat.draft).trim();
    if (!text || !sessionId) return;
    if (composerSubmitPendingRef.current) return;
    if (chatJob) return;
    composerSubmitPendingRef.current = true;
    try {
      const result = await chat.send({
        text,
        source_kind: "typed",
        transcript_revision_id: transcript.transcript?.revision.id ?? null,
      });
      chat.setDraft("");
      setVoiceReviewActive(false);
      attachChatJob(result.jobId);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to send message");
    } finally {
      composerSubmitPendingRef.current = false;
    }
  };

  const handleAttach = async (file: File) => {
    if (!sessionId) return;
    try {
      const result = await audio.uploadFile(file);
      const job = await audio.startTranscription(result.audio_asset_id);
      attachTranscriptionJob(job.job_id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    }
  };

  const handleStartMeetingRecording = async () => {
    await meetingRecorder.start();
  };

  const handleStopMeetingRecording = async () => {
    const result = await meetingRecorder.stop();
    if (!result || !sessionId) return;
    try {
      const uploaded = await audio.uploadRecording(result.blob, result.fileName);
      const job = await audio.startTranscription(uploaded.audio_asset_id);
      attachTranscriptionJob(job.job_id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Recording upload failed");
    }
  };

  const handleStartCommand = async () => {
    await commandRecorder.start();
  };

  const handleStopCommand = async () => {
    const result = await commandRecorder.stop();
    if (!result || !sessionId) return;
    try {
      const response = await voiceApi.sendVoiceCommand(
        sessionId,
        result.blob,
        result.fileName,
        { sendMode: "review_then_send" },
      );
      if (response.warning) {
        toast.warning(response.warning);
      }
      if (response.transcribed_text.trim()) {
        chat.setDraft(response.transcribed_text.trim());
        setVoiceReviewActive(true);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Voice command failed");
    }
  };

  const toggleVoiceMode = () => {
    if (!sessionId) return;
    if (voiceModeEnabled) {
      conversation.stop();
      setVoiceModeEnabled(false);
      return;
    }
    setVoiceModeEnabled(true);
    void conversation.start({
      sessionId,
      engine: settings?.tts.voice_engine ?? "piper",
      transcriptRevisionId: transcript.transcript?.revision.id ?? null,
      onTurnComplete: () => chat.reload(),
    });
  };

  const handleConfirmAction = async (actionId: string) => {
    if (!sessionId) return;
    setActionBusy(true);
    try {
      await actionsApi.confirmAction(sessionId, actionId);
      chat.reload();
      toast.success("Action confirmed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to confirm action");
    } finally {
      setActionBusy(false);
    }
  };

  const handleCancelAction = async (actionId: string) => {
    if (!sessionId) return;
    setActionBusy(true);
    try {
      await actionsApi.cancelAction(sessionId, actionId);
      chat.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to cancel action");
    } finally {
      setActionBusy(false);
    }
  };

  const handleGenerateTts = async (messageId: string) => {
    try {
      await tts.generate({ message_id: messageId });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "TTS failed");
    }
  };

  const handleEditSegment = async (segmentId: string, text: string) => {
    try {
      await transcript.patchSegment(segmentId, text);
      toast.success("Segment saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save segment");
    }
  };

  const handleEditSpeaker = async (speakerId: string, displayName: string) => {
    try {
      await transcript.patchSpeaker(speakerId, displayName);
      toast.success("Speaker renamed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to rename speaker");
    }
  };

  const chatDisabled =
    !sessionId || commandRecorder.state !== "idle" || !!chatJob;

  const busy = chat.loading || composerSubmitPendingRef.current;

  const composer = useMemo(() => {
    if (!sessionId) return null;
    return (
      <Composer
        draft={chat.draft}
        onDraftChange={chat.setDraft}
        onSubmit={() => submit()}
        onFile={handleAttach}
        onStartMeetingRecording={handleStartMeetingRecording}
        onStopMeetingRecording={handleStopMeetingRecording}
        meetingRecordingState={meetingRecorder.state}
        meetingElapsedMs={meetingRecorder.elapsedMs}
        commandRecordingState={commandRecorder.state}
        commandElapsedMs={commandRecorder.elapsedMs}
        onStartCommand={handleStartCommand}
        onStopCommand={handleStopCommand}
        disabled={chatDisabled}
        commandDisabled={voiceModeEnabled}
        busy={busy}
      >
        {voiceReviewActive ? (
          <div className="pb-2">
            <VoiceReviewBanner
              onDiscard={() => {
                chat.setDraft("");
                setVoiceReviewActive(false);
              }}
            />
          </div>
        ) : null}
      </Composer>
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    sessionId,
    chat.draft,
    meetingRecorder.state,
    meetingRecorder.elapsedMs,
    commandRecorder.state,
    commandRecorder.elapsedMs,
    chatDisabled,
    busy,
    voiceReviewActive,
    voiceModeEnabled,
  ]);

  if (!sessionId) {
    return (
      <div className="flex h-full flex-1 flex-col">
        <ChatHeader session={null} onOpenDrawer={sessionDrawer.show} />
        <EmptyState variant="no-session" onNewSession={onNewSession} />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-1 flex-col">
      <ChatHeader session={session} onOpenDrawer={sessionDrawer.show} />
      <div className="flex-1 overflow-hidden">
        <ChatThread
          sessionId={sessionId}
          messages={chat.messages}
          transcript={transcript.transcript}
          transcriptionJob={transcriptionJob}
          chatJob={chatJob}
          settings={settings}
          ttsStatuses={tts.statuses}
          ttsBusyMessageId={tts.busyMessageId}
          actionBusy={actionBusy || !!chatJob}
          onQuickAction={(prompt) => {
            if (chatJob || composerSubmitPendingRef.current) return;
            void submit(prompt);
          }}
          onEditTranscript={transcriptDrawer.show}
          onConfirmAction={handleConfirmAction}
          onCancelAction={handleCancelAction}
          onGenerateTts={handleGenerateTts}
          getTtsAudioUrl={tts.audioUrl}
          audioSrc={
            audio.audio
              ? sessionAudioUrl(sessionId, audio.audio.audio_asset_id)
              : null
          }
          audioDurationMs={audio.audio?.duration_ms ?? 0}
        />
      </div>
      <VoiceModeBar
        enabled={voiceModeEnabled}
        onToggle={toggleVoiceMode}
        engine={settings?.tts.voice_engine ?? "piper"}
        phase={conversation.phase}
        streamingText={conversation.streamingText}
        error={conversation.error}
      />
      {composer}
      <SessionDrawer
        open={sessionDrawer.open}
        session={session}
        audio={audio.audio}
        meetingRecordingState={meetingRecorder.state}
        transcriptionJob={transcriptionJob}
        onOpenChange={sessionDrawer.onOpenChange}
        onUploadClick={() => {
          // trigger hidden file input via AttachMenu event
          document
            .querySelector<HTMLInputElement>('input[type="file"][accept*="wav"]')
            ?.click();
        }}
        onToggleMeetingRecording={() => {
          if (meetingRecorder.state === "recording") {
            void handleStopMeetingRecording();
          } else {
            void handleStartMeetingRecording();
          }
        }}
      />
      <TranscriptDrawer
        open={transcriptDrawer.open}
        transcript={transcript.transcript}
        busy={transcript.loading}
        error={transcript.error}
        onOpenChange={transcriptDrawer.onOpenChange}
        onSaveSegment={handleEditSegment}
        onSaveSpeaker={handleEditSpeaker}
      />
    </div>
  );
}
