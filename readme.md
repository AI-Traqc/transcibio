# Transcibio

Transcibio macht aus Aufnahmen Text und beantwortet Fragen dazu, getippt oder gesprochen.
Es zeigt, wer was gesagt hat, und jede Antwort verweist auf die passende Stelle in der
Aufnahme. Alles läuft auf Ihrem eigenen Rechner. Internet brauchen Sie nur einmal, um die
Modelle herunterzuladen.

## Funktionen

- **Transkribieren:** Audiodatei (`.mp3`, `.wav`) hochladen oder mit dem Mikrofon
  aufnehmen, mit Sprechern und Zeitstempeln.
- **Bearbeiten:** Transkript korrigieren, Sprecher umbenennen.
- **Chat:** Fragen zur Aufnahme stellen. Jede Antwort zeigt ihre Quellen. Schnellbuttons
  fassen zusammen, listen Kernpunkte auf oder übersetzen.
- **Sprachmodus:** Laut fragen und die Antwort hören, ohne Tastatur. Wer spricht,
  unterbricht die Antwort.
- **Vorlesen:** jede Antwort auf Deutsch oder Englisch.
- **Entwürfe:** schlägt E-Mails und Aufgabenlisten vor und speichert sie als Dateien.

## Modelle

Alle Modelle laufen lokal. Das Startskript lädt die Whisper-Modelle und das Chat-Modell
beim ersten Start herunter, die Sprechererkennung kommt bei der ersten Transkription dazu,
die Stimmen sind enthalten.

| Aufgabe | Modell | Größe | Nötig? |
|---|---|---|---|
| Sprache zu Text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) `small` / `medium` / `large-v3` (in den Settings: Fast / Balanced / Quality) | 0,5 / 1,5 / 3 GB, alle drei beim ersten Start geladen | Ja, Standard ist `medium` |
| Sprechererkennung | [pyannote speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) | < 100 MB | Optional, braucht einen kostenlosen [Hugging-Face-Token](#sprechererkennung) |
| Chat, Zusammenfassungen | Ein [Ollama](https://ollama.com)-Modell, Standard `gemma4:e4b`, größer `gemma4:26b` | 7 / 18 GB | Ja. Ohne gibt der Chat nur einfache feste Antworten |
| Sprachausgabe | Piper `thorsten-high` (Deutsch), Kokoro v1.0 (Englisch) | enthalten | Optional |
| Zweite Transkriptions-Engine | NVIDIA Nemotron 3.5 Transcribe | 22 GB | Optional, braucht viel GPU-Speicher |

Größere Chat-Modelle antworten besser, brauchen aber mehr Speicher. Das Modell lässt sich
jederzeit unter **Settings → Chat** wechseln.

## Voraussetzungen

| | Minimum | Empfohlen |
|---|---|---|
| Arbeitsspeicher | 16 GB | 32 GB |
| Freier Speicherplatz | 30 GB | 50 GB |
| Grafikkarte | nicht nötig (läuft auf der CPU, langsamer) | NVIDIA mit 8 GB oder mehr |

Läuft unter Windows 10/11, macOS und Linux (64 Bit).
Installieren Sie vorher:

1. [Docker Desktop](https://docs.docker.com/get-docker/), unter Linux genügt Docker Engine
   ([Warum Docker?](#warum-docker))
2. [Ollama](https://ollama.com/download) für das Chat-Modell

Mit NVIDIA-Grafikkarte unter Linux zusätzlich das
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
Unter Windows reicht ein aktueller NVIDIA-Treiber.

## Installation und Start

**1. Herunterladen**

```bash
git clone https://github.com/ahmad-alismail/transcibio-app.git
```

Ohne Git: auf GitHub **Code → Download ZIP** klicken und entpacken.

**2. Per Doppelklick starten**

| System | Doppelklick auf |
|---|---|
| Windows | `Transcibio.bat` |
| macOS | `Transcibio.command` |
| Linux | Desktop-Symbol **Transcibio** |

Die Dateien liegen im Projektordner. Unter Linux legen Sie das Symbol einmal im Terminal
an: `scripts/transcibio.sh install`.

Ein Fenster zeigt den Start, dann öffnet sich die App im Browser unter
**<http://localhost:8080>**. Solange das Fenster offen ist, läuft Transcibio.
**Beenden:** im Fenster **Strg+C** drücken (Mac: **control+C**). Das gibt den
Arbeitsspeicher frei; Ihre Sitzungen bleiben erhalten.

Als Symbol auf dem Desktop: unter Windows Rechtsklick auf die `.bat`-Datei →
**Senden an → Desktop (Verknüpfung erstellen)** (Windows 11: zuerst
**Weitere Optionen anzeigen**), unter macOS die `.command`-Datei ins Dock ziehen.

**Beim ersten Start** richtet das Startskript alles selbst ein:

1. Es legt die Einstellungsdatei `.env` an und fragt nach Ihrem Hugging-Face-Token
   (optional, Enter überspringt).
2. Es lädt das Chat-Modell herunter (7 GB).
3. Es baut die App (mehrere GB, 10 bis 30 Minuten).
4. Es lädt alle drei Whisper-Modelle (zusammen etwa 5 GB). Damit ist jede
   Genauigkeitsstufe in den Settings sofort nutzbar.

Danach startet die App in wenigen Sekunden. Laufen Docker Desktop oder Ollama nicht,
startet das Skript sie (Windows, macOS).

**Ein Klick auf jedem Gerät.** Das Startskript erkennt das Gerät und wählt die passende
Einrichtung:

| Gerät | Transkription läuft auf | Chat-Modell |
|---|---|---|
| Laptop oder PC mit NVIDIA-GPU | GPU | `gemma4:e4b` |
| Laptop oder PC ohne NVIDIA-GPU | CPU | `gemma4:e4b` |
| Mac | CPU (Docker kann die Apple-GPU nicht nutzen, das Chat-Modell nutzt sie über Ollama) | `gemma4:e4b` |

**Aktualisieren:** `git pull`, dann wie gewohnt starten. Mit ZIP: neue Version entpacken
und den Ordner `data/` sowie die Datei `.env` hineinkopieren. In `data/` liegen Ihre
Sitzungen. Sie bleiben bei Neustarts und Updates erhalten.

## Bedienung

1. **Sitzung anlegen:** In der Seitenleiste auf **New session** klicken. Eine Sitzung
   enthält eine Aufnahme und den Chat dazu.
2. **Aufnahme hinzufügen:** Auf **+** neben dem Eingabefeld klicken, dann
   **Upload meeting audio** oder **Record meeting**. Zum Ausprobieren liegen zwei Beispiele
   im Projektordner: `Test_Kunde_Handwerker.wav` und `transcibio.mp3`.
3. **Transkript lesen:** **Show transcript** zeigt, wer wann gesprochen hat. Mit
   **Edit transcript** korrigieren Sie Wörter und benennen Sprecher um
   (`SPEAKER_00` → `Anna`).
4. **Fragen stellen:** Eine Frage eintippen, zum Beispiel *„Wann ist der Termin?“*, oder
   einen Schnellbutton wie **Zusammenfassen** klicken. Zahlen wie `[1]` zeigen, woher die
   Antwort stammt. **Play** liest die Antwort vor (dazu **TTS enabled** in den Settings
   einschalten).
5. **Sprechen statt tippen:** **Sprachmodus** klicken, laut fragen, zuhören. Wer spricht,
   unterbricht die Antwort. Mit Kopfhörern hört sich die App nicht selbst.
6. **Einstellungen:** **Settings** in der Seitenleiste: Transkriptions-Engine und
   Genauigkeit, Sprechererkennung, Chat-Modell, Denkmodus (Thinking mode), deutsche oder
   englische Stimme.

Sie können den Assistenten auch fragen, wie Transcibio funktioniert oder welche Modelle es
nutzt.

## Konfiguration

Die meisten Einstellungen nehmen Sie in der App unter **Settings** vor. Die Datei `.env`
entsteht beim ersten Start und enthält, was die App zum Starten braucht.

| Variable | Laptop | Ab 32 GB GPU-Speicher | Bedeutung |
|---|---|---|---|
| `TRANSCIBIO_OLLAMA_MODEL` | `gemma4:e4b` | `gemma4:26b` | Chat-Modell. Das Startskript lädt es bei Bedarf herunter. |
| `TRANSCIBIO_OLLAMA_NUM_CTX` | `32768` | `131072` | Wie viel Text das Chat-Modell auf einmal liest. Zusammenfassungen erfassen etwa 30–60 Minuten Besprechung (`32768`) oder 3–5 Stunden (`131072`). Mehr Text braucht mehr Speicher. |
| `TRANSCIBIO_PROFILE` | `balanced` | `quality` | Whisper-Modell zu Beginn: `fast` (small), `balanced` (medium), `quality` (large-v3). |
| `HF_TOKEN` | Ihr Token | Ihr Token | Sprechererkennung, siehe unten. |

Nach einer Änderung an `.env` die App beenden und neu starten. Alle Variablen mit
Erklärung stehen in [`.env.example`](.env.example).

### Sprechererkennung

Das Modell ist kostenlos, Hugging Face verlangt aber, dass Sie den Nutzungsbedingungen
zustimmen:

1. Ein Konto bei [Hugging Face](https://huggingface.co/join) anlegen.
2. Auf der Seite
   [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)
   den Bedingungen zustimmen.
3. Unter [Settings → Access Tokens](https://huggingface.co/settings/tokens) einen Token mit
   *Read*-Rechten erstellen.
4. Den Token beim ersten Start eingeben oder später in `.env` als `HF_TOKEN=hf_...`
   eintragen und die App neu starten.

## Warum Docker?

Transcibio braucht Python, PyTorch für Ihre Grafikkarte, FFmpeg und zwei Sprachausgaben mit
ihren Modellen. Docker installiert all das in einem Schritt, auf jedem System gleich und
getrennt vom Rest des Rechners. Das Startskript bedient Docker für Sie, Docker-Befehle
müssen Sie nicht kennen.

Ollama läuft außerhalb von Docker. So nutzt es die Grafikkarte direkt (auch auf dem Mac)
und steht auch anderen Programmen zur Verfügung.

**Ohne Docker:** Die [Entwicklungsumgebung](docs/development.md) startet die App direkt
mit Python und Node (`node start.mjs`). Das sind mehr Schritte, und die Stimmen laden Sie
selbst herunter.

## Häufige Probleme

| Problem | Lösung |
|---|---|
| Windows: „Der Computer wurde durch Windows geschützt“ | **Weitere Informationen → Trotzdem ausführen** |
| macOS: Die Startdatei lässt sich nicht öffnen | Rechtsklick auf die Datei, **Öffnen** wählen und bestätigen. |
| „Docker laeuft nicht“ | Docker Desktop öffnen und warten, bis es läuft. Linux: `sudo systemctl start docker` |
| „Ollama ist nicht erreichbar“ | Die Ollama-App öffnen. Linux: `systemctl start ollama` |
| Keine Sprecher erkannt | `HF_TOKEN` eintragen und den Modellbedingungen zustimmen ([Sprechererkennung](#sprechererkennung)). |
| Transkription dauert lange | **Settings → Transcription → Whisper model** auf **Fast** stellen. Am meisten hilft eine NVIDIA-GPU. |
| Rechner wird langsam, Speicher reicht nicht | Ein kleineres Chat-Modell wählen oder `TRANSCIBIO_OLLAMA_NUM_CTX` senken (mindestens `16384`). |
| „Invalid host header“ | Die App über `http://localhost:8080` öffnen. |
| Upload wird abgelehnt | Nur `.mp3`- und `.wav`-Dateien sind möglich. |
| Transkription scheitert mit „Nemotron“ | Der Nemotron-Server läuft nicht. In den Settings zurück auf Whisper stellen. |
| Etwas anderes | Logs ansehen: `scripts/transcibio.sh logs` (Windows, in PowerShell: `scripts\transcibio.ps1 logs`) |

## Weitere Dokumentation

Auf Englisch:

- [`docs/docker.md`](docs/docker.md): Docker-Einrichtung im Detail, Befehle von Hand
- [`docs/development.md`](docs/development.md): ohne Docker, Tests, Lint
- [`docs/architecture.md`](docs/architecture.md): Aufbau der App

## Lizenz

Der Quellcode steht unter der [MIT-Lizenz](LICENSE). Das Diarisierungsmodell
`pyannote/speaker-diarization-community-1` wird nicht mitgeliefert, fällt nicht unter
diese Lizenz und hat eigene Nutzungsbedingungen auf Hugging Face, die Sie vor der
Verwendung prüfen und akzeptieren müssen. Dasselbe gilt für weitere Modelle, die die App
herunterlädt (z. B. faster-whisper, Piper, Kokoro, Nemotron).
