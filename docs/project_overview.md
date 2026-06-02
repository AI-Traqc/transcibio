# Transcibio — Your On-Device Audio Assistant

## Table of Contents

- [What is Transcibio?](#what-is-transcibio)
- [Why Transcibio?](#why-transcibio)
- [Who Benefits?](#who-benefits)
- [How Can You Use It?](#how-can-you-use-it)
- [How Is It Built?](#how-is-it-built)
- [Technologies Used](#technologies-used)
- [How Does It Work?](#how-does-it-work)
  - [Transcription Pipeline](#1-transcription-pipeline)
  - [Chat and Retrieval](#2-chat-and-retrieval)
  - [Voice Commands](#3-voice-commands)
  - [Streaming Voice Mode](#4-streaming-voice-mode)
  - [Action Proposals](#5-action-proposals)
  - [Text-to-Speech](#6-text-to-speech)
- [System Architecture](#system-architecture)
- [For Researchers and Developers](#for-researchers-and-developers)
  - [Data Model](#data-model)
  - [Retrieval Strategy](#retrieval-strategy)
  - [Provider Abstraction](#provider-abstraction)
  - [Graceful Degradation](#graceful-degradation)
  - [Background Job System](#background-job-system)
  - [Transcript Versioning](#transcript-versioning)
  - [Extending Transcibio](#extending-transcibio)
- [Contributing](#contributing)

---

## What is Transcibio?

Transcibio is an audio assistant that runs entirely on your computer. You give it an audio recording — a meeting, an interview, a lecture, a voice memo — and it turns that audio into a readable transcript. Once you have a transcript, you can chat with it: ask questions, search for specific topics, and get answers grounded in what was actually said. You can also chat without any transcript at all and use Transcibio as a general local assistant. With **streaming voice mode** you can hold a continuous, hands-free spoken conversation — speak a question and hear the answer read back in real time. Transcibio can also suggest follow-up actions like drafting an email or creating a task list, and it can read responses back to you using text-to-speech.

The key idea: **nothing leaves your machine**. Your audio, your transcripts, your conversations — all of it stays local. No cloud services, no third-party servers, no data uploads.

---

## Why Transcibio?

Transcibio exists to solve two problems at once.

### The privacy problem

Most transcription tools send your audio to remote servers for processing. This works well for casual use, but it becomes a real concern when the audio contains sensitive information — legal discussions, medical consultations, financial reviews, private interviews, or internal company meetings. Even when services promise encryption and data deletion, you are still trusting a third party with your most sensitive conversations.

Transcibio removes that trust requirement entirely. Every component — speech-to-text, speaker identification, language model, text-to-speech — runs locally on your hardware. Your data never touches an external server.

### The productivity problem

Important conversations happen every day, but the insights from those conversations often get lost. Manual note-taking is unreliable. Going back to re-listen to a full recording is time-consuming. And searching through hours of audio for one specific moment is impractical.

Transcibio makes recorded conversations searchable and interactive. Instead of re-listening, you ask a question and get an answer with a direct reference to the relevant part of the transcript. Instead of writing meeting notes from memory, you let the system identify action items and draft follow-ups.

---

## Who Benefits?

### Professionals handling sensitive conversations

Lawyers reviewing client consultations. Doctors revisiting patient discussions. Journalists protecting source confidentiality. Consultants working under NDA. For these users, uploading audio to a cloud service may violate regulations or ethical obligations. Transcibio gives them transcription and analysis capabilities without any data leaving their control.

### Researchers and developers

AI and ML researchers who want to study or extend a working local-first pipeline — from speech recognition to retrieval-augmented generation — without cloud dependencies. Developers who need a practical reference for integrating local AI models into a full-stack application. The entire codebase is open-source and designed around clean interfaces that make it straightforward to swap, extend, or study individual components.

### Teams and organizations

Companies that need meeting transcription and follow-up tracking but cannot (or prefer not to) send internal discussions through external services. IT departments that want to offer AI-powered meeting tools while keeping all data within the corporate network.

---

## How Can You Use It?

Here is the general workflow, from audio to actionable output:

```
                          ┌─────────────────────┐
                          │  You have an audio   │
                          │  recording           │
                          └──────────┬──────────┘
                                     │
                              Upload or record
                                     │
                                     v
                          ┌─────────────────────┐
                          │  Transcibio transcribes │
                          │  the audio locally   │
                          └──────────┬──────────┘
                                     │
                         Identifies speakers (optional)
                                     │
                                     v
                          ┌─────────────────────┐
                          │  You get a full      │
                          │  transcript with     │
                          │  timestamps          │
                          └──────────┬──────────┘
                                     │
                            Review and edit if needed
                                     │
                                     v
                          ┌─────────────────────┐
                          │  Ask questions about │
                          │  the transcript      │
                          └──────────┬──────────┘
                                     │
                          Answers cite specific moments
                                     │
                                     v
                          ┌─────────────────────┐
                          │  Get suggested       │
                          │  follow-up actions   │
                          │  (emails, tasks,     │
                          │   notes)             │
                          └─────────────────────┘
```

**Step 1: Upload or record audio.** You can upload an existing audio file (MP3, WAV, WebM, and other common formats) or record directly in the browser.

**Step 2: Transcribe.** Transcibio converts the audio to text using a local speech recognition model. If speaker identification is enabled, it labels who said what. You choose between three quality levels — fast (quick but less accurate), balanced (good quality at reasonable speed), or quality (highest accuracy, slower).

**Step 3: Review the transcript.** The transcript appears with timestamps and speaker labels. You can edit any segment directly — fix a misheard word, correct a name, rename a speaker. Every edit creates a new version, so nothing is lost.

**Step 4: Chat with the transcript.** Type a question (or speak it using voice commands) and get an answer that references specific parts of the transcript. The system finds the most relevant segments and uses a local language model to compose a grounded response. Each answer includes citations pointing back to exact timestamps.

**Step 5: Act on insights.** When the assistant detects something actionable — like "we should send an update to the team" — it proposes a follow-up action (email draft, task list, note export). You review the proposal and confirm or dismiss it. Confirmed actions produce exportable files.

---

## How Is It Built?

Transcibio has two main parts: a backend that handles all the heavy processing, and a frontend that provides the user interface.

```
┌──────────────────────────────────────────────────────────────┐
│                        Your Browser                          │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │              React Frontend (TypeScript)              │   │
│   │                                                      │   │
│   │  Sidebar          Chat View         Transcript View  │   │
│   │  ┌──────┐   ┌──────────────────┐   ┌────────────┐   │   │
│   │  │List  │   │ Messages         │   │ Segments   │   │   │
│   │  │of    │   │ with citations   │   │ with       │   │   │
│   │  │sess- │   │ and actions      │   │ timestamps │   │   │
│   │  │ions  │   │                  │   │ and        │   │   │
│   │  │      │   │ Composer with    │   │ speakers   │   │   │
│   │  │      │   │ text + voice     │   │            │   │   │
│   │  └──────┘   └──────────────────┘   └────────────┘   │   │
│   └──────────────────────┬───────────────────────────────┘   │
│                          │ HTTP requests                     │
└──────────────────────────┼───────────────────────────────────┘
                           │
                           v
┌──────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (Python)                    │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │                    REST API Layer                     │   │
│   │   /sessions  /chat  /voice  /actions  /settings ...  │   │
│   └──────────────────────┬───────────────────────────────┘   │
│                          │                                   │
│   ┌──────────────────────v───────────────────────────────┐   │
│   │                 Service Layer                         │   │
│   │                                                      │   │
│   │  Transcription    Chat         Action    TTS         │   │
│   │  Orchestrator     Orchestrator Orchestrator          │   │
│   │       │               │            │                 │   │
│   │       v               v            v                 │   │
│   │  ┌─────────┐   ┌──────────┐  ┌──────────┐           │   │
│   │  │ STT     │   │ Retrieval│  │ Export   │           │   │
│   │  │ Diariz. │   │ LLM     │  │ Engine   │           │   │
│   │  │ Assembly│   │ Citations│  │          │           │   │
│   │  └─────────┘   └──────────┘  └──────────┘           │   │
│   └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│   ┌──────────────────────v───────────────────────────────┐   │
│   │              SQLite Database + File Storage           │   │
│   │   Sessions, transcripts, chat, actions, audio files  │   │
│   └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
                           │
            Communicates with local AI providers
                           │
              ┌────────────┼───────────────┐
              v            v               v
        ┌──────────┐ ┌──────────┐   ┌──────────┐
        │ Faster   │ │ Ollama / │   │  Piper   │
        │ Whisper  │ │ LM Studio│   │  (TTS)   │
        │ (STT)    │ │ (LLM)   │   │          │
        └──────────┘ └──────────┘   └──────────┘
```

**Frontend** — A React application built with TypeScript and Vite. It provides the session list, chat interface, transcript viewer/editor, voice recording, and settings. It communicates with the backend through a REST API.

**Backend** — A Python application built with FastAPI. It exposes the REST API, orchestrates all AI processing, manages background jobs, and stores everything in a local SQLite database. Audio files are saved to disk alongside the database.

**Local AI providers** — Separate programs that run on your machine and handle the actual AI work. The backend communicates with them over local HTTP or subprocess calls. Each provider is optional — the system works with whatever is available and degrades gracefully when something is missing.

---

## Technologies Used

| Component | Technology | What it does |
|-----------|-----------|--------------|
| **Backend framework** | FastAPI (Python) | Handles HTTP requests, routing, and input validation |
| **Database** | SQLite | Stores sessions, transcripts, chat history, and settings locally |
| **Speech-to-text** | Faster-Whisper | Converts audio to text using OpenAI's Whisper models, optimized for speed |
| **Speaker identification** | pyannote.audio | Detects and labels different speakers in the audio |
| **Language model** | Ollama or LM Studio | Runs large language models locally for chat, transcript correction, and action proposals |
| **Text-to-speech** | Piper, Kokoro | Converts text responses to spoken audio (Piper for German, Kokoro for English) |
| **Voice activity detection** | Silero VAD (`@ricky0123/vad-web`) | Detects when you start and stop speaking, in the browser, for hands-free voice mode |
| **Audio processing** | FFmpeg | Converts between audio formats (MP3, WAV, WebM, etc.) |
| **Frontend framework** | React + TypeScript | Builds the browser-based user interface |
| **Build tool** | Vite | Bundles and serves the frontend during development and production |
| **UI components** | shadcn/ui | Provides pre-built, accessible interface components |

All AI providers run locally. Faster-Whisper runs directly inside the Python backend. Ollama and LM Studio are separate applications that expose a local HTTP API — the backend sends requests to `localhost` and never to the internet. Piper runs as a local subprocess.

---

## How Does It Work?

### 1. Transcription Pipeline

When you upload audio and start transcription, the system runs a multi-stage pipeline:

```
 Audio file (MP3, WAV, etc.)
       │
       v
 ┌───────────────────────┐
 │  Audio Storage         │  Validates format, extracts metadata
 │                        │  (duration, sample rate, channels)
 └───────────┬───────────┘
             │
             v
 ┌───────────────────────┐
 │  Speech-to-Text (STT) │  Faster-Whisper processes the audio
 │                        │  and outputs timestamped text segments
 │  "Hello everyone,     │  with word-level timing
 │   let's get started"  │
 └───────────┬───────────┘
             │
             v
 ┌───────────────────────┐
 │  Speaker Diarization  │  pyannote.audio identifies who spoke
 │                        │  when, producing speaker segments:
 │  0:00-0:15 Speaker A  │  "Speaker A from 0s to 15s,
 │  0:15-0:42 Speaker B  │   Speaker B from 15s to 42s"
 └───────────┬───────────┘
             │
             v
 ┌───────────────────────┐
 │  Transcript Assembly  │  Merges the text segments with speaker
 │                        │  labels, aligns timestamps, and stores
 │  Speaker A [0:00]:    │  everything as a single transcript
 │  "Hello everyone..."  │  revision in the database
 │  Speaker B [0:15]:    │
 │  "Thanks, let me..."  │
 └───────────────────────┘
```

**Quality presets** control the tradeoff between speed and accuracy:

| Preset | Whisper Model | Best for |
|--------|--------------|----------|
| Fast | `small` | Quick previews, short recordings |
| Balanced | `medium` | General use — good accuracy at reasonable speed |
| Quality | `large-v3` | Important recordings where accuracy matters most |

The entire pipeline runs as a background job. The frontend polls for progress and shows a progress bar as each stage completes.

### 2. Chat and Retrieval

When a transcript is available, you can ask questions about it. The chat system uses **retrieval-augmented generation (RAG)** — a technique where the system first finds relevant information, then uses a language model to compose an answer based on that information.

A transcript is **optional**, though. With no transcript loaded, chat acts as a general local assistant and answers from the language model's own knowledge. When a transcript is present, the system blends the two: it cites the transcript when the question relates to what was said, and falls back to general knowledge when the transcript does not cover the question.

```
 Your question: "What did they decide about the deadline?"
       │
       v
 ┌───────────────────────────────┐
 │  Retrieval                    │  Searches the transcript for segments
 │                               │  related to your question using
 │  Finds: 3 relevant segments  │  text similarity matching
 │  about "deadline" discussion  │
 └──────────────┬────────────────┘
                │
                v
 ┌───────────────────────────────┐
 │  Prompt Construction          │  Builds a prompt for the language
 │                               │  model containing:
 │  "Given these transcript      │  - The relevant transcript segments
 │   segments, answer the        │  - Your question
 │   user's question..."         │  - Instructions to cite sources
 └──────────────┬────────────────┘
                │
                v
 ┌───────────────────────────────┐
 │  Language Model (Ollama)      │  Generates an answer grounded in
 │                               │  the transcript, with references
 │  "They agreed to push the    │  to specific segments
 │   deadline to March 15th     │
 │   [segment 23]..."           │
 └──────────────┬────────────────┘
                │
                v
 ┌───────────────────────────────┐
 │  Citation Extraction          │  Maps segment references to
 │                               │  timestamps, speaker names,
 │  [0:45] Speaker B: "Let's   │  and quote excerpts
 │  move it to March 15th"      │
 └───────────────────────────────┘
```

This means the assistant does not make things up — every answer is tied to something that was actually said in the recording.

If no language model is running, the system falls back to a simpler mode: it still finds and returns the most relevant transcript segments, formatted as bullet points, without generating a composed answer.

### 3. Voice Commands

Instead of typing, you can speak your question. Transcibio records your voice in the browser, sends the audio to the backend, transcribes it locally using Faster-Whisper, and either:

- Shows you the transcribed text for review before sending (review mode), or
- Sends it directly as a chat message (auto-send mode)

This creates a fully hands-free workflow: speak a question, hear the answer via text-to-speech.

### 4. Streaming Voice Mode

Voice mode turns the single-shot voice command into a **continuous, hands-free conversation**. You enable it with the "🔊 Sprachmodus" toggle above the chat composer and then simply talk — no per-turn button. Transcibio listens, answers out loud, and listens again, looping until you switch it off.

```
 You speak
       │
       v
 ┌───────────────────────────────┐
 │  Voice activity detection     │  A browser-side Silero VAD listens
 │  (Silero VAD, in the browser) │  continuously and detects when you
 │                               │  start and stop talking
 └──────────────┬────────────────┘
                │ utterance audio
                v
 ┌───────────────────────────────┐
 │  Speech-to-text               │  The utterance is transcribed locally
 │  (Faster-Whisper)             │  via the existing voice-command path;
 │                               │  the spoken language is detected
 └──────────────┬────────────────┘
                │ text + language  (WebSocket: /api/v1/voice-turn)
                v
 ┌───────────────────────────────┐
 │  Language model (streaming)   │  Tokens stream back as the answer is
 │                               │  generated, grounded in the transcript
 │                               │  when one is loaded, general otherwise
 └──────────────┬────────────────┘
                │ token stream
                v
 ┌───────────────────────────────┐
 │  Sentence chunking            │  A German-aware chunker splits the
 │  (SentenceChunker)            │  stream into speakable sentences; the
 │                               │  first chunk flushes early for low latency
 └──────────────┬────────────────┘
                │ per-sentence text
                v
 ┌───────────────────────────────┐
 │  Streaming TTS (raw PCM)      │  Each sentence is synthesized as it
 │  Piper (German) / Kokoro (EN) │  arrives while the next is still being
 │                               │  generated
 └──────────────┬────────────────┘
                │ PCM frames
                v
 ┌───────────────────────────────┐
 │  Gapless playback             │  The browser plays the sentences back-
 │  (Web Audio)                  │  to-back so the answer sounds continuous
 └───────────────────────────────┘
```

Key properties:

- **Hands-free loop.** After the assistant finishes speaking, Transcibio automatically starts listening again. The whole exchange runs without touching the keyboard or mouse.
- **Barge-in.** If you start talking while the assistant is speaking, its playback is cut immediately and your new turn is captured — just like interrupting a person.
- **Language matching.** The reply is spoken in the language you used. German speech is answered in German (Piper voice `de_DE-thorsten-high`), English in English (Kokoro voice).
- **Two engines.** The voice-mode engine is chosen in Settings → "Voice-mode engine": **Piper** for German (22.05 kHz) and **Kokoro** for English (24 kHz).
- **Works with or without a transcript.** Like typed chat, voice mode is grounded in the transcript when one is loaded and acts as a general assistant otherwise.
- **Low latency.** Warm time-to-first-audio is around 2.3 seconds, dominated by the local language model; the TTS step itself adds only a few milliseconds. Streaming tokens, early first-chunk flushing, and per-sentence synthesis keep the answer flowing.
- **Fully local.** The Silero VAD model and its ONNX runtime assets are bundled under `frontend/public/vad/` (installed via `npm run setup:vad` / postinstall), and the TTS models live under `data/`. Nothing is fetched from a CDN at runtime.

> **Tip:** headphones are recommended. Over a loudspeaker, the assistant's own voice can be picked up by the microphone and trigger barge-in on itself.

### 5. Action Proposals

When the assistant detects something actionable in the conversation — a decision that needs communication, a task that needs tracking, or information that should be saved — it generates an **action proposal**. Types include:

- **Email drafts** — pre-written emails based on what was discussed
- **Task lists** — structured to-do items extracted from the conversation
- **Note exports** — formatted summaries for documentation
- **Document exports** — longer-form output

Each proposal appears in the chat with a preview. You review it and either confirm (which generates an exportable file) or dismiss it. Nothing is sent or saved without your approval.

### 6. Text-to-Speech

When enabled, the assistant's responses can be read aloud using a local text-to-speech engine. Per-message TTS uses Piper. Streaming voice mode (above) can use either **Piper** (German) or **Kokoro** (English), selected in Settings. This is all optional — if no TTS engine is installed, chat continues normally without audio output.

---

## System Architecture

Here is how all the pieces connect at a technical level:

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Frontend (Browser)                         │
│                                                                     │
│  React + TypeScript + Vite                                          │
│  Components: AppShell, Sidebar, ChatView, Composer, TranscriptView  │
│  Voice recording via WebRTC MediaRecorder                           │
│  Hands-free voice mode via browser Silero VAD + Web Audio playback  │
│  Real-time updates via Server-Sent Events (SSE)                     │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
              REST API (HTTP) + WebSocket (voice mode)
                           /api/v1/*
                                │
┌───────────────────────────────v─────────────────────────────────────┐
│                         Backend (FastAPI)                            │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      API Router Layer                        │    │
│  │                                                             │    │
│  │  /sessions ─── create, list, get, update, delete            │    │
│  │  /sessions/{id}/audio ─── upload, record                    │    │
│  │  /sessions/{id}/transcription-jobs ─── start transcription  │    │
│  │  /sessions/{id}/transcript ─── get, edit, correct           │    │
│  │  /sessions/{id}/chat ─── messages, voice commands           │    │
│  │  /voice-turn ─── WebSocket: streamed spoken conversation     │    │
│  │  /sessions/{id}/actions ─── list, confirm, cancel           │    │
│  │  /settings ─── user preferences                             │    │
│  │  /jobs/{id} ─── poll job progress                           │    │
│  │  /health ─── system status                                  │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             │                                       │
│  ┌──────────────────────────v──────────────────────────────────┐    │
│  │                    Service Layer                             │    │
│  │                                                             │    │
│  │  TranscriptionOrchestrator ── coordinates STT + diarization │    │
│  │  ChatOrchestrator ────────── retrieval + LLM + citations    │    │
│  │  ActionOrchestrator ──────── detect + execute proposals     │    │
│  │  TtsOrchestrator ─────────── text-to-speech synthesis       │    │
│  │  AudioStorageService ─────── validate + store audio files   │    │
│  │  TranscriptRetriever ─────── text similarity search         │    │
│  │  TranscriptCorrectionSvc ─── LLM-powered proofreading      │    │
│  │  ModelDiscoveryService ───── detect available AI models     │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             │                                       │
│  ┌──────────────────────────v──────────────────────────────────┐    │
│  │               Background Job Runtime                        │    │
│  │                                                             │    │
│  │  Worker thread polls SQLite for queued jobs                 │    │
│  │  Executes: transcription, chat replies, corrections         │    │
│  │  Reports progress via events (SSE to frontend)              │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             │                                       │
│  ┌──────────────────────────v──────────────────────────────────┐    │
│  │                    Storage Layer                             │    │
│  │                                                             │    │
│  │  SQLiteStore ── sessions, transcripts, chat, actions,       │    │
│  │                 jobs, settings (single DB file)             │    │
│  │  File system ── audio files under data/sessions/<id>/audio/ │    │
│  │                 exports under data/sessions/<id>/exports/   │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         v                    v                    v
  ┌────────────┐      ┌────────────┐       ┌────────────┐
  │  Faster    │      │  Ollama    │       │   Piper    │
  │  Whisper   │      │  or        │       │   (DE) /   │
  │            │      │  LM Studio │       │  Kokoro    │
  │ In-process │      │ HTTP API   │       │   (EN)     │
  │ Python lib │      │ localhost  │       │ Subprocess │
  └────────────┘      └────────────┘       │ / in-proc  │
  Speech-to-text      Language model        └────────────┘
  + diarization       (chat, correct,       Text-to-speech
  (pyannote)          actions)              (per-msg + voice mode)
```

### Key design decisions

**Orchestrator pattern.** Each major feature (transcription, chat, actions, TTS) has its own orchestrator — a service that coordinates multiple smaller components. This keeps individual pieces simple and testable while the orchestrator handles the workflow logic.

**Protocol-based providers.** AI providers (STT, LLM, TTS, diarization) are defined as Python Protocol classes — essentially interfaces. This means you can swap out Faster-Whisper for a different STT engine by implementing the same interface, without changing any other code.

**Immutable transcript revisions.** Every transcript change (initial transcription, manual edit, speaker rename, LLM correction) creates a new revision rather than modifying the existing one. This gives you full edit history and the ability to undo any change.

**Background job queue.** Long-running operations (transcription, chat reply generation) are handled by a background worker thread that polls a job queue in SQLite. The frontend polls for job status and receives progress updates via Server-Sent Events.

**Graceful degradation.** The system is designed to work with whatever is available. Missing an optional provider? The feature degrades to a simpler mode rather than failing entirely. This makes Transcibio usable even with a minimal setup.

---

## For Researchers and Developers

This section covers technical details that may be relevant if you want to understand, study, or extend Transcibio.

### Data Model

All data is stored in a single SQLite database. The key entities and their relationships:

```
assistant_sessions
  │
  ├── audio_assets              (uploaded/recorded audio files)
  │
  ├── transcript_revisions      (immutable snapshots — each edit creates a new one)
  │     ├── transcript_speakers (named speakers within a revision)
  │     ├── transcript_segments (timestamped text chunks)
  │     └── transcript_words    (word-level timing data)
  │
  ├── transcript_edit_operations  (audit trail: who changed what)
  │
  ├── transcript_correction_proposals  (LLM-suggested fixes, pending/applied/rejected)
  │
  ├── chat_threads              (one per session)
  │     └── chat_messages       (user and assistant messages)
  │           ├── message_citations  (links to transcript segments)
  │           └── action_proposals   (suggested follow-ups)
  │                 ├── action_executions  (execution history)
  │                 └── export_artifacts   (generated files)
  │
  ├── voice_commands            (voice input records)
  │
  └── jobs                      (background task queue)
```

Transcript revisions form a linked chain via `parent_revision_id`, giving you a complete history. Each revision records its source (initial transcription, manual edit, speaker rename, or LLM correction), the STT model used, detected language, and any warnings.

### Retrieval Strategy

The chat system uses sparse lexical retrieval rather than dense neural embeddings. This is a deliberate choice:

1. **No embedding model required.** Dense retrieval needs a separate embedding model (often hundreds of megabytes). Sparse retrieval works with basic text processing.
2. **Predictable behavior.** Lexical matching is easier to debug and reason about.
3. **Good enough for single-document search.** When searching within one transcript (rather than millions of documents), lexical retrieval captures most relevant segments effectively.

The implementation tokenizes transcript segments and the query, computes TF-normalized vectors, and ranks by cosine similarity. Top-K results are formatted as context for the language model.

If you need higher-quality retrieval for your use case, the `TranscriptRetriever` is a Protocol — you can implement a dense embedding version without changing the rest of the system.

### Provider Abstraction

Each external AI capability is defined as a Python Protocol (interface):

```
STT:          SttClient          → FasterWhisperSttClient
Diarization:  DiarizationClient  → PyannoteDiarizationClient
LLM:          ChatModelClient    → OllamaChatModelClient
                                 → LmStudioChatModelClient
                                 → RuleBasedChatModelClient (fallback)
TTS:          TtsClient          → PiperTtsClient
Voice mode:   StreamingTtsEngine → PiperStreamingEngine (German)
                                 → KokoroStreamingEngine (English)
```

To add a new provider, implement the matching Protocol and wire it into the orchestrator. No changes needed elsewhere.

### Graceful Degradation

The system follows a consistent pattern: try the preferred provider, catch failures, fall back to a simpler alternative, and record the degradation as a warning in the result object.

| Missing component | What happens |
|------------------|-------------|
| Faster-Whisper | Transcription is unavailable. Voice commands return editable placeholder text. |
| pyannote.audio | Transcription works but all speakers are labeled as unknown. A warning is recorded in the revision. |
| Ollama / LM Studio | Chat returns bullet-point summaries from retrieval results instead of composed answers. Transcript correction is unavailable. |
| Piper | Per-message text-to-speech is disabled. All text-based features continue working. |
| Voice-mode engine (Piper/Kokoro) | If the selected streaming engine cannot be built (missing binary or model), voice mode reports a clear error; typed chat and per-message TTS continue working. |
| FFmpeg | Audio format conversion fails. Native formats (WAV) still work. |
| HF_TOKEN | pyannote models cannot be downloaded. Same as missing pyannote. |

Warnings are collected in result objects (not raised as exceptions), so the caller always gets a result and can decide how to present degraded output.

### Background Job System

Long-running tasks use a job queue stored in SQLite:

1. An API endpoint creates a job record (status: `queued`).
2. A background worker thread polls for queued jobs on a short interval.
3. The worker runs the job, updating `progress` (0.0 to 1.0) and emitting stage events.
4. The frontend polls the job endpoint or listens via SSE for real-time progress.
5. On completion, the job status moves to `completed` or `failed`.

Jobs are typed (`transcribe_audio`, `chat_reply`, etc.) and their results are stored as JSON in the job record. The runtime supports cancellation — a canceled job stops at the next progress checkpoint.

### Transcript Versioning

Transcripts use an append-only versioning model:

```
Revision 1 (source: initial_transcription)
    │
    v
Revision 2 (source: manual_segment_edit, parent: rev 1)
    │
    v
Revision 3 (source: speaker_rename, parent: rev 2)
    │
    v
Revision 4 (source: llm_correction, parent: rev 3)
```

Each revision is immutable once created. The session tracks the `active_transcript_revision_id` pointing to the latest version. This design means:

- You can view any historical version of the transcript.
- The `transcript_edit_operations` table records exactly what changed between revisions.
- LLM correction proposals reference a specific base revision and can be rejected without side effects.
- Concurrent edits are detected (editing is rejected if the revision has changed since the client last fetched it).

### Extending Transcibio

Common extension points:

**Add a new LLM provider.** Implement the `ChatModelClient` Protocol (a `generate` method that takes a prompt and returns text). Register it as an option in the configuration.

**Add a new STT engine.** Implement the `SttClient` Protocol (a `transcribe` method that takes an audio path and returns timestamped segments).

**Add a new action type.** Extend the action detection logic in `ActionOrchestrator` and add an executor for the new type.

**Improve retrieval quality.** Implement the `TranscriptRetriever` Protocol with a dense embedding strategy (e.g., using sentence-transformers). The rest of the chat pipeline remains unchanged.

**Add a new export format.** The export system is file-based — add a new writer that produces the desired format and register it as an executor.

---

## Contributing

Transcibio is open-source. Contributions are welcome — whether that is fixing a bug, adding a new provider integration, improving the UI, or enhancing documentation.

The codebase follows these conventions:

- **Python 3.10**, formatted with Ruff (line length 100)
- **Type hints everywhere**, using `|` union syntax
- **Tests use fakes, not mocks** — simple implementations with preset data
- **Assertions use plain `assert`**
- **Services are defined as Protocol classes** for easy swapping
- **Dataclasses prefer `frozen=True`** with tuple for sequences

**Continuous integration.** Every push to `main` and every pull request runs `.github/workflows/ci.yml`: `ruff check`, `ruff format --check`, and `pytest` for the backend (dependencies installed with `uv pip install`), plus `tsc -b` and `vitest` for the frontend. CI installs only the light dependencies — the optional ML stack (`torch`, `pyannote.audio`, `faster-whisper`, Kokoro) is imported lazily and faked in tests — so it skips the CUDA wheels and runs in seconds. Run the same lint/format/test commands locally before pushing.

See the project README for setup instructions and development workflow.
