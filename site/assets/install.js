/* Step-by-step installation guide. Asks for the system (and GPU), then shows only the steps
   that apply, with copy buttons, saved progress (localStorage, this browser only) and a replay
   of what the launcher prints on the first start (messages from scripts/transcibio.*). */
(() => {
  "use strict";

  const mountEl = document.getElementById("install-wizard");
  if (!mountEl || !window.TB) return;
  const { icon, escapeHtml: esc } = window.TB;

  const REPO = "https://github.com/AI-Traqc/transcibio";
  const ZIP_URL = `${REPO}/archive/refs/heads/main.zip`;
  const STORE_KEY = "transcibio-install-v1";

  function detectOs() {
    const ua = navigator.userAgent || "";
    const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
    const mobile = /Android|iPhone|iPad|iPod/i.test(ua);
    let os = "windows";
    if (/Mac/i.test(platform) || /Mac OS X/i.test(ua)) os = "mac";
    else if (/Linux|X11/i.test(platform) && !/Android/i.test(ua)) os = "linux";
    return { os, mobile };
  }

  const detected = detectOs();
  const defaultOs = () => (detected.os === "linux" ? "linux" : "windows");
  let state = { os: defaultOs(), gpu: null, done: {}, open: null, dl: "zip" };
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORE_KEY) || "null");
    if (saved && typeof saved === "object") state = { ...state, ...saved };
    if (!["windows", "linux"].includes(state.os)) state.os = defaultOs();
  } catch {
    /* private mode: no saved progress */
  }
  const save = () => {
    try {
      window.localStorage.setItem(STORE_KEY, JSON.stringify(state));
    } catch {
      /* ignore */
    }
  };

  // ---------------------------------------------------------------- helpers

  const file = (name) => `<span class="file-chip">${icon("fileText")}${esc(name)}</span>`;
  const folder = () => (state.dl === "git" ? "transcibio" : "transcibio-main");
  const code = (lines, { prompt = "$" } = {}) => {
    const list = Array.isArray(lines) ? lines : [lines];
    const text = list.filter((l) => !l.startsWith("#")).join("\n");
    const html = list
      .map((l) =>
        l.startsWith("#") ? `<span class="comment">${esc(l)}</span>` : `${prompt ? `<span class="prompt">${prompt} </span>` : ""}${esc(l)}`,
      )
      .join("\n");
    return `<div class="code" data-copy="${esc(text)}">${html}<button class="copy-btn" type="button" aria-label="Befehl kopieren">${icon("copy")}<span>Kopieren</span></button></div>`;
  };
  const callout = (kind, html) =>
    `<div class="callout${kind ? ` is-${kind}` : ""}">${icon(kind === "warn" ? "alert" : kind === "ok" ? "checkCircle" : "info")}<div>${html}</div></div>`;
  const ext = (href, label) => `<a href="${href}" target="_blank" rel="noopener">${label}</a>`;
  const spark = () => state.os === "linux" && state.gpu === "spark";
  const chatModel = () => (spark() ? "gemma4:26b" : "gemma4:e4b");
  const chatSize = () => (spark() ? "18 GB" : "7 GB");
  const paste = () =>
    ({ windows: "Rechtsklick oder <kbd>Strg</kbd>+<kbd>V</kbd>", linux: "<kbd>Strg</kbd>+<kbd>Umschalt</kbd>+<kbd>V</kbd>" })[state.os];

  const LICENSE_NOTE = callout(
    "",
    "<p>Docker Desktop ist kostenlos für Privatpersonen, Bildung, gemeinnützige Projekte und kleine Unternehmen (unter 250 Beschäftigten und unter 10 Mio. US-Dollar Jahresumsatz). Größere Unternehmen brauchen ein bezahltes Docker-Abo.</p>",
  );

  // ---------------------------------------------------------------- steps

  function steps() {
    const os = state.os;
    const list = [];

    // 1. Docker
    if (spark()) {
      list.push({
        id: "docker",
        title: "Docker prüfen",
        sub: "Auf dem DGX Spark meist schon vorhanden",
        time: "2 Min.",
        body: `<p>Auf dem DGX Spark sind Docker und die NVIDIA-Unterstützung in der Regel vorinstalliert. Prüfen Sie es kurz im Terminal:</p>
          ${code("docker run hello-world")}
          ${callout("ok", "<p>Erscheint „Hello from Docker!“, ist alles bereit.</p>")}
          <p>Kommt „permission denied“, fügen Sie Ihr Konto der Gruppe <code>docker</code> hinzu und melden Sie sich danach ab und wieder an:</p>
          ${code("sudo usermod -aG docker $USER")}`,
      });
    } else if (os === "linux") {
      list.push({
        id: "docker",
        title: "Docker Engine installieren",
        sub: "Startet die App in einem abgeschlossenen Bereich",
        time: "10 Min.",
        body: `<p>Folgen Sie der offiziellen Anleitung für Ihre Distribution: ${ext("https://docs.docker.com/engine/install/", "Docker Engine installieren")} (Ubuntu, Debian, Fedora und andere). Docker Desktop brauchen Sie unter Linux nicht.</p>
          <p>Danach fügen Sie Ihr Konto einmal der Gruppe <code>docker</code> hinzu, damit Transcibio ohne <code>sudo</code> läuft:</p>
          ${code("sudo usermod -aG docker $USER")}
          <p>Melden Sie sich ab und wieder an (oder starten Sie neu). Dann testen:</p>
          ${code("docker run hello-world")}
          ${callout("ok", "<p>Erscheint „Hello from Docker!“, ist Docker bereit.</p>")}
          <p class="a-muted" style="color:var(--muted);font-size:14px">Gut zu wissen: Mitglieder der Gruppe <code>docker</code> haben weitreichende Rechte auf dem Rechner. Das ist bei Docker so üblich.</p>`,
      });
    } else {
      list.push({
        id: "docker",
        title: "Docker Desktop installieren",
        sub: "Startet die App in einem abgeschlossenen Bereich",
        time: "10 Min.",
        body: `<ol>
            <li>Laden Sie ${ext("https://docs.docker.com/desktop/setup/install/windows-install/", "Docker Desktop für Windows")} herunter.</li>
            <li>Öffnen Sie ${file("Docker Desktop Installer.exe")} und klicken Sie sich mit den vorgeschlagenen Einstellungen durch. Der Haken bei <b>WSL 2</b> bleibt gesetzt.</li>
            <li>Starten Sie den Rechner neu, wenn der Installer darum bittet.</li>
            <li>Öffnen Sie Docker Desktop einmal und akzeptieren Sie die Nutzungsbedingungen. Eine Anmeldung bei Docker ist nicht nötig, Sie können sie überspringen.</li>
            <li>Warten Sie, bis unten links <b>Engine running</b> steht.</li>
          </ol>
          ${callout("warn", "<p>Fragt Windows nach <b>WSL</b> oder <b>Virtualisierung</b>: Bestätigen Sie die Installation und starten Sie neu. Docker Desktop richtet das selbst ein.</p>")}
          ${LICENSE_NOTE}`,
      });
    }

    // 2. GPU (only where it matters)
    if (os === "windows") {
      list.push({
        id: "gpu",
        title: "NVIDIA-Treiber aktualisieren",
        sub: "Damit Transcibio die Grafikkarte nutzen kann",
        time: "5 Min.",
        body: `<p>Docker Desktop gibt Ihre NVIDIA-Grafikkarte an Transcibio weiter, wenn der Treiber aktuell ist.</p>
          <ol>
            <li>Laden Sie den aktuellen Treiber von ${ext("https://www.nvidia.com/de-de/drivers/", "nvidia.com")} (oder über die NVIDIA-App) und installieren Sie ihn.</li>
            <li>Starten Sie den Rechner neu.</li>
          </ol>
          <p>Mehr ist nicht nötig. Passt alles, steht beim Start im Startfenster „mit NVIDIA-GPU“.</p>`,
      });
    }
    if (os === "linux" && !spark()) {
      list.push({
        id: "gpu",
        title: "NVIDIA Container Toolkit installieren",
        sub: "Damit Docker die Grafikkarte nutzen kann",
        time: "10 Min.",
        body: `<ol>
            <li>Prüfen Sie, ob der NVIDIA-Treiber läuft:${code("nvidia-smi")}Erscheint eine Tabelle mit Ihrer Grafikkarte, ist der Treiber da. Sonst installieren Sie ihn zuerst über Ihre Distribution (Ubuntu: „Zusätzliche Treiber“).</li>
            <li>Installieren Sie das ${ext("https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html", "NVIDIA Container Toolkit")} nach der offiziellen Anleitung.</li>
            <li>Verbinden Sie es mit Docker und starten Sie Docker neu:${code(["sudo nvidia-ctk runtime configure --runtime=docker", "sudo systemctl restart docker"])}</li>
          </ol>
          <p>Das Startprogramm erkennt die Grafikkarte danach selbst; im Startfenster steht beim Start „mit NVIDIA-GPU“.</p>`,
      });
    }
    if (spark()) {
      list.push({
        id: "gpu",
        title: "DGX Spark: größere Modelle",
        sub: "Passiert automatisch",
        time: "1 Min.",
        body: `<p>Das Startprogramm erkennt den DGX Spark und wählt automatisch die größeren Modelle: <code>gemma4:26b</code> für den Chat und Whisper <code>large-v3</code> für die Transkription.</p>
          ${callout("", `<p><b>Optional: Nemotron 3.5 Transcribe</b> als zweite Transkriptions-Engine. Tragen Sie dazu nach dem ersten Start <code>COMPOSE_PROFILES=nemotron</code> in die Datei <code>.env</code> im Projektordner ein und starten Sie Transcibio neu. Der Server braucht etwa 36 GB Speicher und rund 5 Minuten zum Laden; die Einstellungen zeigen solange „Server is starting“.</p>`)}`,
      });
    }

    // 3. Ollama
    const ollamaBody = {
      windows: `<ol>
          <li>Laden Sie ${ext("https://ollama.com/download/windows", "Ollama für Windows")} herunter und installieren Sie es.</li>
          <li>Ollama läuft danach im Hintergrund (Lama-Symbol unten rechts in der Taskleiste). Ein Fenster müssen Sie nicht offen lassen.</li>
        </ol>`,
      linux: `<p>Installieren Sie Ollama mit dem Befehl von der ${ext("https://ollama.com/download/linux", "offiziellen Ollama-Seite")}:</p>
        ${code("curl -fsSL https://ollama.com/install.sh | sh")}
        <p>Ollama läuft danach als Dienst im Hintergrund. Test:</p>${code("ollama --version")}`,
    }[os];
    list.push({
      id: "ollama",
      title: "Ollama installieren",
      sub: "Führt das Chat-Modell auf Ihrem Rechner aus",
      time: "5 Min.",
      body: `${ollamaBody}${callout("ok", `<p>Das Chat-Modell (<code>${chatModel()}</code>, etwa ${chatSize()}) müssen Sie nicht selbst laden. Das erledigt Transcibio beim ersten Start.</p>`)}`,
    });

    // 4. Hugging Face token (optional)
    list.push({
      id: "hf",
      title: "Sprechererkennung freischalten",
      sub: "Damit das Transkript zeigt, wer spricht",
      time: "5 Min.",
      optional: true,
      body: `<p>Für die Sprechererkennung braucht Transcibio ein kostenloses Modell von Hugging Face. Ohne diesen Schritt funktioniert alles andere, das Transkript zeigt dann nur keine Sprecher.</p>
        <ol>
          <li>Legen Sie ein kostenloses Konto an: ${ext("https://huggingface.co/join", "huggingface.co/join")}.</li>
          <li>Öffnen Sie ${ext("https://huggingface.co/pyannote/speaker-diarization-community-1", "pyannote/speaker-diarization-community-1")} und stimmen Sie den Nutzungsbedingungen zu.</li>
          <li>Erstellen Sie unter ${ext("https://huggingface.co/settings/tokens", "Settings → Access Tokens")} einen neuen Token vom Typ <b>Read</b>.</li>
          <li>Kopieren Sie den Token (er beginnt mit <code>hf_</code>) und halten Sie ihn bereit. Sie fügen ihn beim ersten Start ein.</li>
        </ol>
        ${callout("warn", "<p>Behandeln Sie den Token wie ein Passwort: nicht weitergeben und nirgends öffentlich einfügen.</p>")}`,
    });

    // 5. Download
    const unzip = {
      windows: `<p>Rechtsklick auf die Datei ${file("transcibio-main.zip")} im Ordner Downloads → <b>Alle extrahieren…</b> → einen Ort wählen, zum Beispiel <b>Dokumente</b>. Es entsteht der Ordner ${file("transcibio-main")}.</p>`,
      linux: `<p>Entpacken Sie die Datei, zum Beispiel in Ihren Benutzerordner:</p>${code(["cd ~", "unzip ~/Downloads/transcibio-main.zip"])}`,
    }[os];
    const gitHint = {
      windows: `Git für Windows gibt es unter ${ext("https://git-scm.com/download/win", "git-scm.com")}. Den Befehl geben Sie in PowerShell ein, zum Beispiel im Ordner Dokumente.`,
      linux: "Git installieren Sie über Ihre Distribution, zum Beispiel <code>sudo apt install git</code>.",
    }[os];
    list.push({
      id: "download",
      title: "Transcibio herunterladen",
      sub: "Als ZIP-Datei oder mit Git",
      time: "2 Min.",
      body: `<div class="tabs" role="tablist" aria-label="Download-Art">
          <button role="tab" aria-selected="${state.dl === "zip"}" data-dl="zip">Als ZIP (einfach)</button>
          <button role="tab" aria-selected="${state.dl === "git"}" data-dl="git">Mit Git</button>
        </div>
        ${
          state.dl === "zip"
            ? `<p><a class="btn btn-primary btn-small" href="${ZIP_URL}">${icon("download")}ZIP herunterladen</a></p>${unzip}`
            : `${code(["git clone https://github.com/AI-Traqc/transcibio.git", "cd transcibio"], { prompt: os === "windows" ? "PS>" : "$" })}<p>${gitHint} Updates holen Sie später mit <code>git pull</code>.</p>`
        }`,
    });

    // 6. Start
    const startBody = {
      windows: `<ol>
          <li>Öffnen Sie den Ordner ${file(folder())}.</li>
          <li>Doppelklicken Sie auf ${file("Transcibio.bat")}. Sind Dateiendungen ausgeblendet, heißt sie nur „Transcibio“ (Typ „Windows-Batchdatei“).</li>
          <li>Erscheint „Der Computer wurde durch Windows geschützt“: Klicken Sie auf <b>Weitere Informationen</b> → <b>Trotzdem ausführen</b>.</li>
        </ol>`,
      linux: `<p>Öffnen Sie ein Terminal im Projektordner und legen Sie einmal das Desktop-Symbol an:</p>
        ${code([`cd ~/${folder()}`, "scripts/transcibio.sh install"])}
        <p>Ab jetzt starten Sie Transcibio per Doppelklick auf das Symbol <b>Transcibio</b>. Oder direkt im Terminal:</p>
        ${code("scripts/transcibio.sh start")}
        <p class="a-muted" style="color:var(--muted);font-size:14px">Meldet das Terminal „Permission denied“, starten Sie mit <code>bash scripts/transcibio.sh install</code>.</p>`,
    }[os];
    list.push({
      id: "start",
      title: "Transcibio starten",
      sub: "Beim ersten Mal richtet sich alles selbst ein",
      time: "20–40 Min. beim ersten Mal",
      body: `${startBody}
        <p><b>Beim ersten Start</b> lädt das Programm alles Nötige herunter und baut die App. Das dauert einmalig 20 bis 40 Minuten; danach startet Transcibio in wenigen Sekunden. So sieht es aus:</p>
        <div id="term-mount"></div>`,
    });

    // 7. Use
    const stopKey = "<kbd>Strg</kbd>+<kbd>C</kbd>";
    const shortcut = {
      windows: "<li><b>Symbol auf dem Desktop:</b> Rechtsklick auf <code>Transcibio.bat</code> → <b>Senden an → Desktop (Verknüpfung erstellen)</b>. Unter Windows 11 zuerst <b>Weitere Optionen anzeigen</b>.</li>",
      linux: "",
    }[os];
    list.push({
      id: "use",
      title: "Loslegen",
      sub: "Die App öffnet sich im Browser",
      time: "",
      body: `<p>Der Browser öffnet sich von selbst mit <b>http://localhost:8080</b>. Falls nicht, tippen Sie die Adresse selbst ein. Die Adresse funktioniert nur auf diesem Rechner.</p>
        <ul>
          <li><b>Ausprobieren:</b> Im Projektordner liegt die Beispielaufnahme ${file("Test_Kunde_Handwerker.wav")}. Legen Sie eine neue Sitzung an und laden Sie die Datei hoch, wie im Demo oben.</li>
          <li><b>Beenden:</b> Im Transcibio-Fenster ${stopKey} drücken oder das Fenster schließen. Ihre Sitzungen bleiben erhalten.</li>
          <li><b>Nächstes Mal:</b> Einfach wieder starten. Jetzt dauert es nur wenige Sekunden.</li>
          ${shortcut}
          <li><b>Aktualisieren:</b> ${
            state.dl === "git"
              ? "Im Projektordner <code>git pull</code> ausführen, dann wie gewohnt starten."
              : "Neue ZIP-Datei laden und entpacken. Kopieren Sie den Ordner <code>data</code> und die Datei <code>.env</code> aus dem alten Ordner in den neuen. Darin liegen Ihre Sitzungen und Einstellungen."
          }</li>
        </ul>`,
    });

    return list;
  }

  // ---------------------------------------------------------------- terminal replay

  function terminalScript() {
    const os = state.os;
    const dir = folder();
    const envPath = { windows: `C:\\Users\\…\\Documents\\${dir}\\.env`, linux: `/home/…/${dir}/.env` }[os];
    const label = spark() ? "DGX Spark" : "mit NVIDIA-GPU";
    const envLabel = spark() ? "DGX Spark: gemma4:26b, Whisper large-v3" : "Laptop: gemma4:e4b, Whisper medium";
    const model = chatModel();
    const size = spark() ? "18 GB" : "7.2 GB";
    const lines = [];
    const add = (text, cls = "", delay = 450, caption = null) => lines.push({ text, cls, delay, caption });
    if (os === "windows") {
      add("==> Starte Docker Desktop ...", "info", 600, "Läuft Docker Desktop noch nicht, startet das Programm es selbst.");
    }
    add(`==> Einstellungen angelegt: ${envPath} (${envLabel})`, "info", 900, "Beim ersten Start legt das Programm die Einstellungsdatei an und wählt passende Modelle für Ihren Rechner.");
    add("");
    add("Sprechererkennung (optional): Hugging Face Token einfuegen.", "", 300);
    add('Anleitung: readme.md, Abschnitt "Sprechererkennung". Spaeter aenderbar in .env.', "", 300);
    add("Token (Enter = ueberspringen): hf_••••••••••••••••", "", 2200, `Hier fügen Sie den Token aus dem Schritt „Sprechererkennung“ ein (${paste()}) und drücken Enter. Ohne Token drücken Sie einfach Enter.`);
    add("");
    add(`==> Lade das Chat-Modell ${model} herunter (einmalig, mehrere GB) ...`, "info", 1000, `Jetzt lädt Ollama das Chat-Modell (${size.replace(".", ",")}). Je nach Internet dauert das 5 bis 20 Minuten.`);
    add("pulling manifest", "dim", 400);
    add(`pulling model: 100% ▕████████████████████▏ ${size}`, "dim", 1200);
    add("success", "ok", 500);
    add(`==> Starte Transcibio (${label}). Der erste Start dauert eine Weile ...`, "info", 900, "Die App wird gebaut und gestartet. Beim ersten Mal dauert das 10 bis 30 Minuten. Sie können währenddessen etwas anderes machen.");
    add("[+] Building … (einmalig, mehrere GB)", "dim", 1800);
    add(`[+] Running 2/2`, "dim", 300);
    add(` ✔ Container ${dir}-backend-1   Started`, "ok", 300);
    add(` ✔ Container ${dir}-frontend-1  Started`, "ok", 500);
    add("==> Warte, bis Transcibio bereit ist ...", "info", 1000);
    add("==> Pruefe Whisper-Modelle (beim ersten Start ca. 5 GB) ...", "info", 1400, "Zum Schluss lädt das Programm die drei Whisper-Modelle (zusammen etwa 5 GB). Danach ist jede Genauigkeitsstufe sofort nutzbar.");
    add("");
    add("==> Transcibio laeuft: http://localhost:8080", "info", 500, "Fertig! Der Browser öffnet sich mit Transcibio. Lassen Sie dieses Fenster offen, solange Sie arbeiten.");
    add("==> Dieses Fenster offen lassen. Beenden: Strg+C druecken.", "info", 0);
    return lines;
  }

  const term = { timer: 0, i: 0, playing: false, caption: "" };

  function termMarkup() {
    const windows = state.os === "windows";
    return `<div class="term${windows ? " is-windows" : ""}">
      <div class="term-bar">${icon("terminal")}<span>${windows ? "Transcibio (PowerShell)" : "Terminal: Transcibio"}</span><span class="spacer"></span>
        <span class="term-controls">
          <button class="btn btn-small btn-secondary" type="button" data-term="play">${icon("play")}<span>Abspielen</span></button>
          <button class="btn btn-small btn-ghost" type="button" data-term="end">${icon("forward")}<span>Bis zum Ende</span></button>
        </span>
      </div>
      <div class="term-screen" aria-live="polite" aria-label="Ausgabe des Startprogramms"><span class="cursor"></span></div>
      <div class="term-caption">${icon("info")}<div data-term-caption>Klicken Sie auf <b>Abspielen</b>, um zu sehen, was beim ersten Start passiert (stark verkürzt).</div></div>
    </div>`;
  }

  function termRender(upto) {
    const screen = mountEl.querySelector(".term-screen");
    const cap = mountEl.querySelector("[data-term-caption]");
    if (!screen) return;
    const lines = terminalScript().slice(0, upto);
    screen.innerHTML = `${lines.map((l) => `<span class="${l.cls}">${esc(l.text)}</span>`).join("\n")}${lines.length ? "\n" : ""}<span class="cursor"></span>`;
    screen.scrollTop = screen.scrollHeight;
    const lastCaption = [...lines].reverse().find((l) => l.caption);
    if (cap && lastCaption) cap.innerHTML = lastCaption.caption;
  }

  function termStop() {
    window.clearTimeout(term.timer);
    term.playing = false;
    const btn = mountEl.querySelector('[data-term="play"] span');
    if (btn) btn.textContent = term.i >= terminalScript().length ? "Nochmal" : term.i ? "Weiter" : "Abspielen";
  }

  function termPlay() {
    const lines = terminalScript();
    if (term.playing) {
      termStop();
      return;
    }
    if (term.i >= lines.length) term.i = 0;
    term.playing = true;
    const btn = mountEl.querySelector('[data-term="play"] span');
    if (btn) btn.textContent = "Pause";
    const step = () => {
      term.i += 1;
      termRender(term.i);
      if (term.i >= lines.length) {
        termStop();
        return;
      }
      term.timer = window.setTimeout(step, lines[term.i - 1].delay);
    };
    step();
  }

  // ---------------------------------------------------------------- rendering

  const REQ = {
    windows: {
      ram: "Einstellungen → System → Info → „Installierter RAM“.",
      disk: "Explorer → <b>Dieser PC</b>: freier Platz auf Laufwerk C:.",
      gpu: "Task-Manager (<kbd>Strg</kbd>+<kbd>Umschalt</kbd>+<kbd>Esc</kbd>) → Leistung → GPU. Dort muss „NVIDIA“ stehen; „Dedizierter GPU-Speicher“ zeigt den Grafikspeicher.",
    },
    linux: {
      ram: "Im Terminal <code>free -h</code>, Zeile „Mem“, Spalte „total“.",
      disk: "Im Terminal <code>df -h ~</code>, Spalte „Avail“.",
      gpu: "Im Terminal <code>nvidia-smi</code>. Die Tabelle zeigt Name und Speicher der Karte (zum Beispiel 8192MiB). Kommt „command not found“, fehlt der NVIDIA-Treiber oder die Karte.",
    },
  };

  function choice(group, value, label, iconName, extra = "") {
    const pressed = state[group] === value;
    return `<button type="button" class="choice" data-choice="${group}" data-value="${value}" aria-pressed="${pressed}">${iconName ? icon(iconName) : ""}${label}${extra}</button>`;
  }

  function render() {
    const os = state.os;
    const list = steps();
    const ids = list.map((s) => s.id);
    const doneCount = ids.filter((id) => state.done[id]).length;
    if (state.open !== "__none__" && (!state.open || !ids.includes(state.open))) {
      state.open = ids.find((id) => !state.done[id]) || null;
    }
    const allDone = doneCount === list.length;
    const req = REQ[os];
    const erkannt = (value) => (detected.os === value && !detected.mobile ? " <small>erkannt</small>" : "");
    const gpuQuestion = `<div class="question">
            <div class="question-label">Hat Ihr Rechner eine NVIDIA-Grafikkarte?</div>
            <div class="choice-row" role="group">
              ${choice("gpu", "yes", "Ja", "cpu")}
              ${choice("gpu", "no", "Nein", "x")}
              ${choice("gpu", "unknown", "Weiß nicht", "help")}
              ${os === "linux" ? choice("gpu", "spark", "NVIDIA DGX Spark", "cpu") : ""}
            </div>
            ${
              state.gpu === "unknown"
                ? `<div class="question-help"><p>So prüfen Sie es: ${req.gpu}</p></div>`
                : state.gpu === "no"
                  ? callout("warn", "<p><b>Ohne NVIDIA-Grafikkarte läuft Transcibio nicht.</b> Sie brauchen einen Windows- oder Linux-Rechner mit NVIDIA-Grafikkarte und mindestens 8 GB Grafikspeicher.</p>")
                  : ""
            }
          </div>`;

    mountEl.innerHTML = `
      <div class="panel">
        <h3>1. Ihr Rechner</h3>
        <p class="panel-sub">Zwei kurze Fragen, dann sehen Sie nur die Schritte, die Sie wirklich brauchen.</p>
        ${detected.mobile ? callout("", "<p>Sie lesen gerade auf dem Handy oder Tablet. Installieren können Sie Transcibio auf einem Windows- oder Linux-Rechner mit NVIDIA-Grafikkarte. Wählen Sie unten, welchen Sie haben.</p>") : ""}
        ${detected.os === "mac" && !detected.mobile ? callout("warn", "<p>Sie nutzen gerade einen Mac. Transcibio braucht eine NVIDIA-Grafikkarte und läuft deshalb nicht auf dem Mac. Installieren Sie es auf einem Windows- oder Linux-Rechner mit NVIDIA-Grafikkarte.</p>") : ""}
        <div class="question">
          <div class="question-label">Welches System nutzen Sie?</div>
          <div class="choice-row" role="group">
            ${choice("os", "windows", "Windows 10/11", "windows", erkannt("windows"))}
            ${choice("os", "linux", "Linux", "linux", erkannt("linux"))}
          </div>
        </div>
        ${gpuQuestion}
        <div class="req-grid">
          <div class="req"><div class="req-title">Arbeitsspeicher</div><div class="req-value">16 GB <small>empfohlen 32 GB</small></div>
            <details><summary>So prüfen Sie das</summary><p>${req.ram}</p></details></div>
          <div class="req"><div class="req-title">Freier Speicherplatz</div><div class="req-value">30 GB <small>empfohlen 50 GB</small></div>
            <details><summary>So prüfen Sie das</summary><p>${req.disk}</p></details></div>
          <div class="req"><div class="req-title">Grafikkarte (nötig)</div><div class="req-value">NVIDIA <small>mindestens 8 GB Grafikspeicher</small></div>
            <details><summary>So prüfen Sie das</summary><p>${req.gpu}</p></details></div>
        </div>
      </div>
${
  state.gpu === "no"
    ? `
      <div class="panel">
        <h3>2. Schritt für Schritt</h3>
        <p class="panel-sub">Die Installationsschritte erscheinen, sobald Ihr Rechner passt. Haben Sie Zugriff auf einen Windows- oder Linux-Rechner mit NVIDIA-Grafikkarte, wählen Sie oben bei der Grafikkarte <b>Ja</b>.</p>
      </div>`
    : `
      <div class="panel">
        <div class="progress-head">
          <h3>2. Schritt für Schritt</h3>
          <span class="progress-text">${doneCount} von ${list.length} erledigt</span>
        </div>
        <div class="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${list.length}" aria-valuenow="${doneCount}" aria-label="Fortschritt"><span style="width:${(doneCount / list.length) * 100}%"></span></div>
        <p class="panel-sub" style="margin-top:12px">Haken Sie jeden Schritt ab. Ihr Fortschritt bleibt in diesem Browser gespeichert, Sie können also jederzeit eine Pause machen.</p>
        <ol class="steps">${list
          .map((s, i) => {
            const done = !!state.done[s.id];
            const open = state.open === s.id;
            return `<li class="step${done ? " is-done" : ""}${open ? " is-open" : ""}" id="step-${s.id}">
              <button type="button" class="step-head" data-step-toggle="${s.id}" aria-expanded="${open}" aria-controls="step-body-${s.id}">
                <span class="step-num">${done ? icon("check") : i + 1}</span>
                <span class="step-title">${s.title}<small>${s.sub}</small></span>
                ${s.optional ? '<span class="step-tag is-optional">optional</span>' : ""}
                ${s.time ? `<span class="step-tag">${s.time}</span>` : ""}
                ${icon("chevronDown", "icon step-chevron")}
              </button>
              <div class="step-body" id="step-body-${s.id}">
                ${s.body}
                <div class="step-done-row">
                  <button type="button" class="btn btn-small ${done ? "btn-secondary" : "btn-primary"}" data-step-done="${s.id}">${icon(done ? "rotate" : "check")}${done ? "Doch noch nicht erledigt" : "Erledigt, weiter"}</button>
                  ${s.optional && !done ? `<button type="button" class="btn btn-small btn-ghost" data-step-done="${s.id}">Überspringen</button>` : ""}
                </div>
              </div>
            </li>`;
          })
          .join("")}</ol>
        ${
          allDone
            ? callout("ok", `<p><b>Geschafft!</b> Transcibio läuft auf Ihrem Rechner. Wenn etwas hakt, hilft der Abschnitt ${'<a href="#hilfe">Hilfe</a>'} weiter.</p>`)
            : ""
        }
        <p class="panel-sub" style="font-size:14px;margin-top:16px">${icon("rotate")} <button type="button" class="link-btn" data-reset style="display:inline;padding:0">Fortschritt zurücksetzen</button></p>
      </div>`
}`;

    const termMount = mountEl.querySelector("#term-mount");
    if (termMount) {
      termMount.innerHTML = termMarkup();
      if (term.i) termRender(term.i);
      termStop();
    }
    if (window.TB.setHelpOs) window.TB.setHelpOs(os);
  }

  mountEl.addEventListener("click", (event) => {
    const t = event.target;
    const choiceBtn = t.closest("[data-choice]");
    if (choiceBtn) {
      state[choiceBtn.dataset.choice] = choiceBtn.dataset.value;
      if (choiceBtn.dataset.choice === "os" && state.os === "windows" && state.gpu === "spark") state.gpu = null;
      term.i = 0;
      save();
      render();
      return;
    }
    const toggle = t.closest("[data-step-toggle]");
    if (toggle) {
      const id = toggle.dataset.stepToggle;
      state.open = state.open === id ? "__none__" : id;
      save();
      render();
      mountEl.querySelector(`[data-step-toggle="${id}"]`)?.focus();
      return;
    }
    const doneBtn = t.closest("[data-step-done]");
    if (doneBtn) {
      const id = doneBtn.dataset.stepDone;
      state.done[id] = !state.done[id];
      if (state.done[id]) {
        const ids = steps().map((s) => s.id);
        const next = ids.slice(ids.indexOf(id) + 1).find((x) => !state.done[x]) || ids.find((x) => !state.done[x]);
        state.open = next || "__none__";
        save();
        render();
        const head = next && mountEl.querySelector(`[data-step-toggle="${next}"]`);
        if (head) {
          head.focus({ preventScroll: true });
          const rect = head.getBoundingClientRect();
          if (rect.top < 80 || rect.top > window.innerHeight - 120) {
            head.scrollIntoView({ behavior: "smooth", block: "center" });
          }
        }
      } else {
        state.open = id;
        save();
        render();
      }
      return;
    }
    const dl = t.closest("[data-dl]");
    if (dl) {
      state.dl = dl.dataset.dl;
      save();
      render();
      return;
    }
    const termBtn = t.closest("[data-term]");
    if (termBtn) {
      if (termBtn.dataset.term === "play") termPlay();
      else {
        termStop();
        term.i = terminalScript().length;
        termRender(term.i);
        termStop();
      }
      return;
    }
    if (t.closest("[data-reset]")) {
      state = { os: defaultOs(), gpu: null, done: {}, open: null, dl: "zip" };
      term.i = 0;
      save();
      render();
    }
  });

  render();
})();
