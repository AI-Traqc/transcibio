export const strings = {
  appName: "Transcibio",
  sidebar: {
    newSession: "New session",
    searchPlaceholder: "Search sessions",
    collapse: "Collapse sidebar",
    expand: "Expand sidebar",
    settings: "Settings",
    theme: "Theme",
    themeLight: "Light",
    themeDark: "Dark",
    themeSystem: "System",
    rename: "Rename",
    delete: "Delete",
    empty: "No sessions yet",
  },
  chat: {
    emptyNoSession: {
      title: "Start a new session",
      subtitle: "Create a session to transcribe audio and chat with it.",
    },
    emptyNoAudio: {
      title: "Upload audio to get started",
      subtitle: "Drop a .mp3 or .wav into the composer, or use the + button.",
    },
    emptyReady: {
      title: "Ask about your meeting",
      subtitle: "Try Summarize, Extract key points, or ask in your own words.",
    },
    you: "You",
    assistant: "Assistant",
    placeholder: "Ask about your meeting or transcript\u2026",
    send: "Send",
    voice: "Voice command",
    attach: "Attach audio",
    transcriptBlockTitle: "Transcript",
    transcriptBlockShow: "Show transcript",
    transcriptBlockHide: "Hide transcript",
    transcriptBlockEdit: "Edit transcript",
    quickActions: {
      summarize: "Zusammenfassen",
      keyPoints: "Kernpunkte extrahieren",
      identifySpeakers: "Sprecher identifizieren",
      translate: "Ins Englische übersetzen",
    },
  },
  composer: {
    voiceReview: {
      title: "Voice command ready",
      description: "Review and edit, then send.",
      dismiss: "Discard",
    },
    recording: "Recording meeting\u2026",
    uploading: "Uploading\u2026",
    transcribing: "Transcribing\u2026",
  },
  status: {
    noAudio: "No audio uploaded",
    transcribing: "Transcribing\u2026",
    ready: "Transcript ready",
    failed: "Something went wrong",
  },
  drawers: {
    session: {
      title: "Session details",
      upload: "Upload meeting audio",
      record: "Record meeting",
      stopRecording: "Stop recording",
      startTranscription: "Start transcription",
    },
    transcript: {
      title: "Edit transcript",
      segments: "Segments",
      speakers: "Speakers",
      correction: "AI correction",
    },
  },
  dialogs: {
    settings: {
      title: "Settings",
      description: "Configure transcription, chat, and speech.",
    },
    rename: {
      title: "Rename session",
      placeholder: "Session title",
      confirm: "Save",
      cancel: "Cancel",
    },
    delete: {
      title: "Delete this session?",
      description:
        "The transcript, chat, and audio for this session will be permanently deleted.",
      confirm: "Delete",
      cancel: "Cancel",
    },
  },
} as const;
