# Transcibio vNext Demo Checklist (v1)

Use this checklist before a live demo. The demo is valid if the happy path works with either local providers or the documented fallback behavior.

## 1. Environment Readiness

1. Run `scripts/check_vnext_env.ps1`
2. Confirm `.venv` Python exists
3. Confirm `ffmpeg` + `ffprobe` are available
4. Confirm `node` + `npm` are available
5. Note optional provider status (LM Studio, Ollama, Piper)

## 2. Start Services

1. Start backend (`uvicorn`) and frontend (`vite`)
2. Open frontend UI and confirm backend health strip is visible
3. Confirm `GET /api/v1/healthz` reports `status=ok`

## 3. Transcript Pipeline

1. Create a new session
2. Upload meeting audio (or record a short clip)
3. Start transcription
4. Verify transcript job progress appears
5. Verify transcript segments + speakers render

## 4. Transcript Editing + Revisions

1. Edit one transcript segment and save
2. Rename one speaker and save
3. Verify new revision appears in revision selector
4. Verify older revision is read-only

## 5. AI Transcript Correction

1. Generate correction proposal (full transcript or selected segments)
2. Review diff preview
3. Apply proposal as a new revision
4. Verify latest revision updates and prior revision remains selectable
5. If no LLM is available, confirm rules-based fallback warning is shown clearly

## 6. Chat + Citations

1. Send a typed or voice-reviewed command
2. Verify assistant reply renders
3. Verify citations render and correspond to transcript spans
4. If no LLM is available, verify fallback label/status is visible

## 7. Action Proposals + Exports

1. Verify an action proposal card appears (email/task/note/doc)
2. Confirm the action
3. Verify status changes to executed
4. Verify artifact link(s) are shown and downloadable

## 8. TTS (Optional Piper)

1. Click `Generate TTS` on an assistant message
2. If Piper is configured: verify audio controls render and playback works
3. If Piper is unavailable: verify a clear error is shown and text chat remains usable

## 9. Streaming Voice Mode

1. Plug in headphones (loudspeaker echo can self-trigger barge-in)
2. Confirm the engine in Settings → "Voice-mode engine" (Piper = German, Kokoro = English)
3. Toggle "🔊 Sprachmodus" on above the chat composer
4. Grant microphone access; confirm the bar shows "Zuhören…" (listening)
5. Speak a question and stop; confirm it transcribes and the assistant starts answering aloud
6. Verify audio plays back gaplessly and the spoken text streams in the bar
7. Verify the reply language matches the spoken language (German → Piper, English → Kokoro)
8. Confirm the loop continues hands-free: after the answer, it listens again without a button press
9. Barge-in: start talking while the assistant is speaking; verify playback cuts immediately and your new turn is captured
10. Switch the engine in Settings, re-run a turn, and verify the new voice/language is used
11. Toggle Sprachmodus off and confirm listening stops
12. If the selected engine is unavailable: verify a clear error is shown and typed chat still works

## 10. Chat Without a Transcript

1. Create or open a session with no transcript (skip the transcription pipeline)
2. Send a typed general-knowledge question
3. Verify the assistant answers from general knowledge (no transcript citations required)
4. Optionally repeat via voice mode and confirm a spoken answer with no transcript

## 11. Session Reopen / Restore

1. Switch sessions (or reopen the same one)
2. Verify transcript revision list restores
3. Verify chat messages, citations, and action status restore
4. Verify TTS metadata (ready/failed) restores on assistant messages

## 12. Failure-Mode UX Spot Check

1. Retry chat reply works without page refresh
2. Retry TTS works without page refresh
3. Correction proposal regenerate/apply retry path is usable
4. Voice mode recovers after a failed turn (still listens on the next utterance)
5. Fallback messages are actionable (not opaque)
