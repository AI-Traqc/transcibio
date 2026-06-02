# Transcibio — Lokale Audio-Transkription & Assistent

**Transcibio** ist ein Assistent, der vollständig auf deinem Gerät läuft. Er transkribiert Audio, erkennt, wer was gesagt hat, und ermöglicht Chat- und Sprachbefehl-Abläufe mit einem lokalen LLM. Zusätzlich gibt es einen freihändigen **Sprachmodus** — du stellst eine Frage laut und hörst die Antwort gesprochen zurück. Alles läuft lokal; keine Daten verlassen den Rechner. Die Oberfläche ist auf Deutsch ausgelegt.

- **Backend**: FastAPI (`backend/app/main.py`) mit einer Hintergrund-Job-Laufzeit, SQLite-Speicherung und Orchestratoren für Transkription, **Diarisierung** (Zuordnung jedes Abschnitts zu einem Sprecher), Chat, Aktionen und **TTS** (Text-zu-Sprache, inklusive Streaming-TTS für den Sprachmodus).
- **Frontend**: React + Vite + TypeScript (`frontend/`). Die Sprachaktivitätserkennung im Browser (VAD, über Silero) steuert den Sprecherwechsel im Sprachmodus; das VAD-Modell und die ONNX-Runtime-Dateien sind lokal eingebunden, damit alles offline funktioniert.
- **Provider** (alle optional, mit sanften Fallbacks): `faster-whisper` (STT, Sprache-zu-Text), `pyannote.audio` (Diarisierung), Ollama / LM Studio (LLM), Piper (deutsches TTS), Kokoro (englisches TTS).

**Der Chat funktioniert mit oder ohne Transkript.** Ohne Transkript ist er ein allgemeiner Assistent; mit Transkript stützt er seine Antworten auf das Transkript (mit Quellenangaben), wenn das passt, und greift sonst auf allgemeines Wissen zurück. Der Assistent antwortet in der Sprache, die du sprichst oder schreibst.

---

## Schnellstart (Windows)

> **Plattform:** Windows ist die primäre Zielplattform — alle Befehle unten verwenden Windows-Pfade (`.venv\Scripts\python.exe`) und -Werkzeuge (`copy`, `winget`). Unter macOS/Linux passt du den venv-Pfad auf `.venv/bin/python` an, verwendest `cp` statt `copy` und installierst FFmpeg über deinen Paketmanager.

### Voraussetzungen

**Erforderlich:**

- **Python 3.10** über [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js 18+** / `npm`
- **FFmpeg** im `PATH` (für die Audio-Verarbeitung):
  ```bash
  winget install -e --id Gyan.FFmpeg
  ffmpeg -version
  ```
- **Ollama** (oder LM Studio), das lokal läuft, für Chat / Transkript-Korrektur. Transcibio nutzt standardmäßig Ollama unter `http://127.0.0.1:11434`. Installiere Ollama und lade dann das Standardmodell:
  ```bash
  ollama pull gpt-oss-20b
  ollama serve            # falls es nicht bereits als Dienst läuft
  ```
  Ein anderes Modell wählst du, indem du `TRANSCIBIO_OLLAMA_MODEL` in `.env` setzt. Ohne ein laufendes LLM funktioniert der Chat weiterhin, greift aber auf einfache, fest vorgegebene Antworten zurück.

**Optional:**

- **Hugging-Face-Token** (`HF_TOKEN`) — nur nötig, wenn du die pyannote-Diarisierung aktivierst. Akzeptiere die Modellbedingungen unter <https://huggingface.co/pyannote/speaker-diarization-community-1>.
- **NVIDIA-GPU / CUDA** — beschleunigt Transkription und Diarisierung (siehe den CUDA-Installationsweg unten).
- **TTS-Modelle für den Sprachmodus** — siehe [Sprachmodus](#sprachmodus-optional) unten.

### 1. Code holen

```bash
git clone https://github.com/ai-traqc/transcibio.git
cd transcibio
```

Führe alle folgenden Befehle aus dem Wurzelverzeichnis des Repositories aus (dem Ordner, der `pyproject.toml` enthält).

### 2. Installieren

```bash
# Python-venv erstellen
uv python install 3.10
uv venv --python 3.10 .venv

# Backend-Abhängigkeiten installieren (CPU)
uv pip install --python .venv\Scripts\python.exe ".[dev]"

# …oder stattdessen mit NVIDIA-GPU / CUDA-Wheels
uv pip install --python .venv\Scripts\python.exe --torch-backend cu128 --reinstall ".[dev]"

# (nur CUDA) prüfen, ob die torch-Installation CUDA unterstützt
.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"

# Frontend-Abhängigkeiten installieren
cd frontend
npm install
cd ..

# Umgebung konfigurieren
copy .env.example .env
# .env bearbeiten — setze mindestens HF_TOKEN, falls du Diarisierung möchtest
```

Das `npm install` im Frontend führt automatisch einen `postinstall`-Schritt aus, der das Silero-VAD-Modell und die ONNX-Runtime-Dateien nach `frontend/public/vad/` kopiert (manuell erneut ausführbar mit `npm run setup:vad`). So bleibt der Sprachmodus vollständig offline.

### 3. Umgebung konfigurieren (`.env`)

Alle Einstellungen sind optional und haben sinnvolle Standardwerte, daher brauchst du `.env` nur, um sie zu überschreiben. Kopiere die Beispieldatei und bearbeite sie nach Bedarf:

```bash
copy .env.example .env      # Windows (unter macOS/Linux: `cp .env.example .env`)
```

Die am häufigsten gesetzten Werte:

- `HF_TOKEN` — dein Hugging-Face-Token, nur nötig, wenn du die pyannote-Diarisierung aktivierst.
- `TRANSCIBIO_OLLAMA_MODEL` — das Ollama-Modell für den Chat (Standard `gpt-oss-20b`).

Die vollständige, kommentierte Liste der Variablen findest du in `.env.example`. `.env` wird von Git ignoriert, deine geheimen Werte landen also nie im Repository.

### 4. Starten

```bash
# Backend (automatischer Neustart bei Änderungen)
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload

# Frontend (separates Terminal, aus frontend/)
cd frontend
npm run dev
```

Dann die App öffnen:

- **Frontend** — der Vite-Dev-Server gibt eine URL aus, üblicherweise <http://localhost:5173>. Öffne sie im Browser; du solltest die deutschsprachige Transcibio-Oberfläche sehen.
- **Backend-API** — <http://127.0.0.1:8000>, mit interaktiver Swagger-Dokumentation unter <http://127.0.0.1:8000/docs>.

Hilfsskripte (PowerShell) automatisieren die Bereitschaftsprüfung und das Starten beider Server:

```powershell
# Bereitschaftsprüfung (FFmpeg + lokale Provider) — führe dies zuerst aus, wenn etwas nicht klappt
powershell -ExecutionPolicy Bypass -File scripts/check_vnext_env.ps1
# Backend + Frontend gemeinsam starten
powershell -ExecutionPolicy Bypass -File scripts/start_vnext.ps1
```

### Status / Provider-Bereitschaft

`GET /api/v1/healthz` meldet die Verfügbarkeit von FFmpeg und der Provider (LM Studio, Ollama, Piper) über Best-Effort-Prüfungen.

### Fallbacks, wenn Provider offline sind

- **Kein lokales LLM** (Ollama / LM Studio nicht verfügbar): Chat und Transkript-Korrektur greifen auf festes, vorhersehbares Verhalten zurück.
- **Kein Piper / Kokoro** (Binary oder Modelle fehlen): TTS und Sprachmodus geben einen klaren Fehlerstatus zurück; der Text-Chat funktioniert weiterhin.
- **Keine `faster-whisper`-Laufzeit**: Die Sprachbefehl-API liefert bearbeitbaren Ersatztext, statt abzustürzen.

---

## Sprachmodus (optional)

Im Sprachmodus führst du ein durchgehendes, freihändiges Gespräch: Du sprichst, es wird transkribiert, die Antwort wird als Sprache zurückgestreamt, und dann hört das System wieder zu — kein Knopfdruck pro Wortbeitrag, und du kannst den Assistenten durch Sprechen unterbrechen (Barge-in). Zwei TTS-Engines lassen sich unter **Einstellungen → „Voice-mode engine"** wählen: **Piper** (Deutsch, Stimme `de_DE-thorsten-high`) und **Kokoro** (Englisch).

> Kopfhörer empfohlen — Echo vom Lautsprecher kann das Barge-in fälschlich auslösen.

**Python-Abhängigkeiten für Kokoro (Englisch):**

```bash
uv pip install --python .venv\Scripts\python.exe kokoro-onnx soundfile
```

**Modelle / Binaries** liegen unter `data/` (von Git ignoriert) und werden einmalig heruntergeladen:

| Engine | Datei(en) | Quelle |
| --- | --- | --- |
| Piper-Binary | `data/bin/piper/piper.exe` | [rhasspy/piper releases](https://github.com/rhasspy/piper/releases) |
| Piper-Stimme (DE) | `data/models/tts/piper/de_DE-thorsten-high.onnx` (+ `.onnx.json`) | HF [`rhasspy/piper-voices`](https://huggingface.co/rhasspy/piper-voices) |
| Kokoro (EN) | `data/models/tts/kokoro/kokoro-v1.0.onnx` und `voices-v1.0.bin` | [thewh1teagle/kokoro-onnx releases](https://github.com/thewh1teagle/kokoro-onnx/releases) |

Optionale Umgebungs-Überschreibungen (die oben gezeigten Standardwerte leiten sich von `TRANSCIBIO_DATA_ROOT` ab):

- `TRANSCIBIO_PIPER_BIN`, `TRANSCIBIO_PIPER_MODEL`
- `TRANSCIBIO_KOKORO_MODEL`, `TRANSCIBIO_KOKORO_VOICES`, `TRANSCIBIO_KOKORO_VOICE` (Standard `af_sarah`)

**Verwendung:** Klicke auf **Sprachmodus** über dem Chat-Eingabefeld, um zu starten. Wähle die Engine in den Einstellungen passend zu deiner Sprache.

> Die Zeit bis zum ersten Ton hängt vom LLM ab: mit dem Standardmodell `gpt-oss-20b` liegt sie warm bei ca. 2,3 s; ein kleineres Modell ist schneller.

## Unterstützte Audioformate

Hochgeladene Audiodateien müssen `.mp3` oder `.wav` sein. Aufnahmen direkt im Browser (`.webm`, `.ogg`, `.m4a`, `.mp4`, `.wav`, `.mp3`) werden akzeptiert und beim Einlesen per FFmpeg in WAV umgewandelt.

**Beispieldateien zum Testen:** Das Repository enthält im Projektstamm zwei Beispielaufnahmen, die du hochladen kannst, um Transkription, Diarisierung und Chat von Anfang bis Ende auszuprobieren:

- `Test_Kunde_Handwerker.wav` — ein deutsches Kunden-/Handwerker-Gespräch (mehrere Sprecher, fordert die Diarisierung).
- `transcibio.mp3` — ein kürzeres MP3-Beispiel.

Dies sind bewusst aufgenommene Demo-Aufnahmen; alle anderen lokalen Daten liegen unter `data/` und werden von Git ignoriert.

---

## Tests

```bash
# Backend (Python)
.venv\Scripts\python.exe -m pytest                          # alles
.venv\Scripts\python.exe -m pytest tests/api                # API-Router-Tests
.venv\Scripts\python.exe -m pytest tests/services           # Service-Tests
.venv\Scripts\python.exe -m pytest tests/services/test_local_llm.py -v

# Frontend
cd frontend
npm run test          # Vitest (Unit / Komponenten)
npm run test:e2e      # Playwright
```

## Lint / Formatierung

```bash
.venv\Scripts\python.exe -m ruff check
.venv\Scripts\python.exe -m ruff check --fix
.venv\Scripts\python.exe -m ruff format
```

## Continuous Integration

Jeder Push auf `main` und jeder Pull Request führt [`.github/workflows/ci.yml`](.github/workflows/ci.yml) aus:

- **Backend** — `ruff check`, `ruff format --check` und `pytest` (Abhängigkeiten installiert mit `uv pip install`).
- **Frontend** — `tsc -b` (Typprüfung) und `vitest`.

Der optionale ML-Stack (`torch`, `pyannote.audio`, `faster-whisper`, Kokoro) wird verzögert importiert und in den Tests durch Fakes ersetzt, sodass CI nur die schlanke Laufzeit + Dev-Werkzeuge installiert und die mehrere GB großen CUDA-Wheels überspringt. Die Befehle oben für Lint, Formatierung und Tests entsprechen exakt dem, was CI prüft — führe sie aus, bevor du pushst.

---

## Mit Docker ausführen (am einfachsten — kein Python-/Node-Setup)

Wenn du die App nur **nutzen** möchtest, ohne Python, Node oder FFmpeg zu installieren, führt Docker das Ganze — Backend, Frontend und deutsche Sprache — mit einem Befehl aus. Es funktioniert unter Windows, macOS und Linux gleich.

### Was du zuerst brauchst

1. **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** installiert und laufend.
   - *Windows + NVIDIA-GPU:* Nutze das **WSL 2**-Backend von Docker Desktop und installiere das NVIDIA-Container-Toolkit, damit die GPU in den Containern sichtbar ist. Keine GPU? Nutze stattdessen den **CPU**-Befehl unten — er läuft nur langsamer.
2. **Ollama, das auf deinem Computer läuft** (für echte KI-Chat-Antworten). Docker startet es **nicht** für dich:
   ```bash
   ollama serve            # starten (falls noch nicht aktiv)
   ollama pull gpt-oss-20b # das Standardmodell, einmaliger Download
   ```
   Ohne Ollama öffnet und funktioniert die App weiterhin, aber der Chat gibt einfache vorgefertigte Antworten statt KI-Antworten.

### Starten

Aus dem Projektstamm (dem Ordner mit `docker-compose.yml`):

```bash
# Mit einer NVIDIA-GPU (schnellere Transkription)
docker compose up --build

# Ohne GPU (nur CPU)
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up --build
```

Der erste Lauf dauert eine Weile (er lädt ca. 13 GB an Abhängigkeiten herunter). Sobald es bereit ist, öffne:

👉 **http://localhost:8080**

Das ist die vollständige App. Zum Stoppen drücke **Strg+C** und führe optional `docker compose down` aus, um die Container zu entfernen.

### Gut zu wissen

- **Beide Sprach-Engines funktionieren sofort** — Piper (Deutsch) und Kokoro (Englisch), mit ihren Modellen, sind im Image enthalten. Wähle eine unter **Einstellungen → „Voice-mode engine"**.
- **Deine Daten werden gespeichert** im Ordner `data/` auf deinem Computer (Datenbank, Aufnahmen, heruntergeladene Modelle), sodass sie Neustarts überstehen.
- **Einstellungen** wie `HF_TOKEN` oder ein anderes `TRANSCIBIO_OLLAMA_MODEL` kommen in eine `.env`-Datei im Projektstamm — sie wird automatisch eingelesen.

Mehr Details und Fehlerbehebung: [`docs/docker.md`](docs/docker.md).

---

## Dokumentation

- [`CLAUDE.md`](CLAUDE.md) — Architektur, Konventionen und eine vollständige Befehlsreferenz.
- [`docs/project_overview.md`](docs/project_overview.md) — Projektübersicht.
- [`docs/demo_checklist_v1.md`](docs/demo_checklist_v1.md) — Checkliste für den Demo-Durchlauf.

## Lizenz

Der Quellcode dieses Repositories steht unter der [MIT-Lizenz](LICENSE).

Wichtige Hinweise zu Drittkomponenten:

- `openai-whisper` und `pyannote.audio` sind eigenständige Drittprojekte und werden upstream unter MIT bereitgestellt.
- Für die Sprecher-Diarisierung verwendet dieses Projekt zusätzlich das Hugging Face-Modell `pyannote/speaker-diarization-community-1`. Dieses Modell wird nicht mit dem Repository ausgeliefert und ist nicht durch die MIT-Lizenz dieses Repositories abgedeckt.
- Die Modellseite für `pyannote/speaker-diarization-community-1` verlangt einen separaten Hugging Face-Zugriff und listet eigene Lizenz- bzw. Nutzungsbedingungen. Prüfen und akzeptieren Sie diese daher immer selbst, bevor Sie die Diarisierung verwenden oder eigene Distributionen mit eingebundenen Modellen weitergeben.
