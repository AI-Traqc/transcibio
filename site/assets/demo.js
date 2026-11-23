/* Clickable demo of the Transcibio app with a guided tour. Everything is simulated in the
   browser: a fictional meeting, prepared answers, no network, no microphone. Labels and layout
   follow the real UI (frontend/src/components); the tour text is German. */
(() => {
  "use strict";

  const root = document.getElementById("demo-app");
  const tourEl = document.getElementById("demo-tour");
  if (!root || !tourEl || !window.TB) return;
  const { escapeHtml: esc } = window.TB;
  const ic = (name, cls = "") => window.TB.icon(name, cls);

  // ---------------------------------------------------------------- demo meeting

  const FILE = { name: "Projektmeeting_Website.mp3", seconds: 169, mime: "audio/mpeg" };
  const AUTO_TITLE = "Website-Relaunch: Zeitplan und Budget";
  const SEGMENTS = [
    [0, 5, "SPEAKER_00", "Guten Morgen zusammen. Fangen wir an mit der neuen Website."],
    [5, 9, "SPEAKER_01", "Gern. Ich habe den Zeitplan mitgebracht."],
    [9, 12, "SPEAKER_02", "Und ich die ersten Entwürfe."],
    [12, 24, "SPEAKER_00", "Prima. Ziel ist, dass die neue Seite Ende März online geht. Heute klären wir Zeitplan, Aufgaben und Budget."],
    [24, 41, "SPEAKER_02", "Ich habe zwei Varianten für die Startseite vorbereitet. Die helle Variante kam bei der Kundin besser an, damit würde ich weitermachen."],
    [41, 47, "SPEAKER_00", "Einverstanden, wir nehmen die helle Variante."],
    [47, 63, "SPEAKER_01", "Zum Zeitplan: Die Technik steht bis Februar. Danach brauchen wir zwei Wochen zum Testen."],
    [63, 72, "SPEAKER_00", "Frau Brandt, den Designentwurf bitte bis Mittwoch."],
    [72, 79, "SPEAKER_02", "Mittwoch schaffe ich. Der Designentwurf kommt als PDF."],
    [79, 91, "SPEAKER_01", "Dann hole ich das Hosting-Angebot ein, am besten zwei Angebote zum Vergleich."],
    [91, 96, "SPEAKER_00", "Gut. Nächster Punkt: Budget."],
    [96, 112, "SPEAKER_01", "Wir haben 12.000 Euro eingeplant, inklusive Hosting für das erste Jahr."],
    [112, 125, "SPEAKER_02", "Neue Fotos kommen noch dazu. Die liegen aber unter tausend Euro."],
    [125, 136, "SPEAKER_00", "Dann beschließen wir 12.000 Euro als Rahmen. Die Fotos kommen extra."],
    [136, 146, "SPEAKER_01", "Soll ich die Kundin über den Zeitplan informieren?"],
    [146, 169, "SPEAKER_00", "Ja, bitte schicken Sie ihr bis Freitag eine kurze Zusammenfassung. Nächstes Treffen ist dann Donnerstag in einer Woche. Vielen Dank Ihnen allen!"],
  ].map(([s, e, spk, text]) => ({ s, e, spk, text }));
  const SPEAKER_KEYS = ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"];

  const QUICK = [
    ["summarize", "Zusammenfassen", "Fasse die wichtigsten Entscheidungen aus dem Transkript zusammen."],
    ["keypoints", "Kernpunkte extrahieren", "Extrahiere die 5 wichtigsten Punkte als Aufzählung."],
    ["speakers", "Sprecher identifizieren", "Versuche die Sprecher anhand ihrer Aussagen zu identifizieren. Schlage Bezeichnungen vor."],
    ["translate", "Ins Englische übersetzen", "Übersetze das Transkript ins Englische."],
  ];

  const DEFAULT_SETTINGS = {
    engine: "whisper-pyannote",
    profile: "balanced",
    diarization: true,
    model: "gemma4:e4b",
    think: false,
    detail: "normal",
    timestamps: true,
    sendMode: "review_then_send",
    voiceEngine: "piper",
    tts: false,
    ttsAuto: false,
    ttsPlay: false,
  };

  // ---------------------------------------------------------------- state + timers

  let S;
  const jobs = new Map();
  const seen = new Set();
  const timers = new Set();
  const voiceTimers = new Set();

  function later(fn, ms, bucket = timers) {
    const id = window.setTimeout(() => {
      bucket.delete(id);
      fn();
    }, ms);
    bucket.add(id);
    return id;
  }
  function clearBucket(bucket) {
    bucket.forEach((id) => window.clearTimeout(id));
    bucket.clear();
  }

  const narrow = () => window.matchMedia("(max-width: 760px)").matches;

  function freshState() {
    return {
      sessions: [
        { id: "ex1", title: "Kundentermin Bäckerei Krause", example: true },
        { id: "ex2", title: "Team-Meeting KW 47", example: true },
        { id: "ex3", title: "Interview Produktfeedback", example: true },
      ],
      currentId: null,
      query: "",
      collapsed: narrow(),
      menu: null,
      overlay: null,
      sheetTab: "segments",
      editingSpeaker: null,
      speakerDraft: "",
      editingSeg: null,
      segDraft: "",
      settings: { ...DEFAULT_SETTINGS },
      draftSettings: null,
      confirmDelete: false,
      voice: { on: false, phase: "idle", text: "", userSpeaking: false, turn: 0 },
      command: { state: "idle", start: 0 },
      review: false,
      dark: false,
      sound: S ? S.sound : true,
      toast: null,
      draft: "",
      ttsBusy: null,
    };
  }

  const uid = () => Math.random().toString(16).slice(2, 8);
  const cur = () => S.sessions.find((s) => s.id === S.currentId && !s.example) || null;
  const fmt = (ms) => {
    const total = Math.max(0, Math.floor(ms / 1000));
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
  };
  const fmtS = (sec) => fmt(sec * 1000);
  const spk = (key) => {
    const s = cur();
    return (s && s.speakers[key]) || key;
  };
  const renamed = (key) => spk(key) !== key;
  const brandt = () => (renamed("SPEAKER_02") ? spk("SPEAKER_02") : "Frau Brandt");
  const chatBusy = (s) => s && s.messages.some((m) => m.status === "running");

  function newSession() {
    const s = {
      id: `s${uid()}`,
      title: "New session",
      phase: "empty",
      recStart: 0,
      transcriptOpen: false,
      messages: [],
      segs: SEGMENTS.map((seg) => ({ ...seg })),
      speakers: Object.fromEntries(SPEAKER_KEYS.map((k) => [k, k])),
      diarized: true,
      revision: 1,
      player: { playing: false, t: 0, since: 0 },
    };
    S.sessions.unshift(s);
    S.currentId = s.id;
    S.draft = "";
    S.review = false;
    stopVoice();
    return s;
  }

  // ---------------------------------------------------------------- speech (optional)

  const synth = "speechSynthesis" in window ? window.speechSynthesis : null;
  let voices = [];
  if (synth) {
    const load = () => (voices = synth.getVoices());
    load();
    synth.addEventListener?.("voiceschanged", load);
  }
  function speak(text, lang, onEnd) {
    if (!synth || !S.sound) return false;
    const voice = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(lang));
    if (!voice) return false;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.voice = voice;
    u.lang = voice.lang;
    u.rate = 1.03;
    if (onEnd) u.onend = onEnd;
    synth.speak(u);
    return true;
  }
  const hush = () => synth && synth.cancel();

  // ---------------------------------------------------------------- staged jobs

  function startJob(id, stages, onDone) {
    const job = { stages, idx: 0, start: Date.now(), stageStart: Date.now() };
    jobs.set(id, job);
    const next = () => {
      if (job.idx >= stages.length) {
        jobs.delete(id);
        onDone();
        return;
      }
      later(() => {
        job.idx += 1;
        job.stageStart = Date.now();
        next();
      }, stages[job.idx].ms);
    };
    next();
    return job;
  }
  const jobStage = (job) => job.stages[Math.min(job.idx, job.stages.length - 1)];
  function jobPct(job) {
    const st = jobStage(job);
    const f = Math.min(1, (Date.now() - job.stageStart) / st.ms);
    return Math.round(st.from + (st.to - st.from) * f);
  }

  // ---------------------------------------------------------------- answers

  function cite(...idx) {
    return idx;
  }

  function answer(question) {
    const s = cur();
    if (!s || s.phase !== "ready") {
      return {
        html: "<p>Zu dieser Sitzung gibt es noch kein Transkript. Laden Sie zuerst eine Aufnahme hoch, dann kann ich Fragen dazu beantworten.</p>",
        cites: [],
      };
    }
    const quick = QUICK.find(([, , prompt]) => prompt === question);
    const t = question.toLowerCase();
    let key = quick ? quick[0] : "fallback";
    if (!quick) {
      if (/e-?mail|mail an|schreib|brief an|nachricht an/.test(t)) key = "email";
      else if (/aufgabe|to-?do|wer macht|wer übernimmt|wer uebernimmt|erledig/.test(t)) key = "tasks";
      else if (/design|entwurf|mittwoch|pdf/.test(t)) key = "design";
      else if (/budget|kost|euro|geld|teuer|preis/.test(t)) key = "budget";
      else if (/hosting|angebot|server/.test(t)) key = "hosting";
      else if (/treffen|nächste|naechste|donnerstag/.test(t)) key = "next";
      else if (/zeitplan|technik|februar|märz|maerz|online|launch|go-live|wann|fertig|test/.test(t)) key = "schedule";
      else if (/zusammenfass|überblick|ueberblick|worum|entscheid|beschl|ergebnis/.test(t)) key = "summarize";
      else if (/kernpunkt|wichtigst|punkte/.test(t)) key = "keypoints";
      else if (/sprecher|wer spricht|wer ist|wer war|teilnehm|identifi/.test(t)) key = "speakers";
      else if (/englisch|english|übersetz|uebersetz|translat/.test(t)) key = "translate";
      else if (/transcibio|modell|lokal|cloud|internet|datenschutz|daten|funktionierst|wie funktioniert|wer bist/.test(t)) key = "app";
      else if (/^(hallo|hi|hey|guten (morgen|tag|abend)|moin|servus)\b/.test(t)) key = "hello";
    }
    const a = spk("SPEAKER_01");
    const k = spk("SPEAKER_00");
    const b = brandt();
    const profile = { fast: "small", balanced: "medium", quality: "large-v3" }[S.settings.profile];
    switch (key) {
      case "design":
        return {
          html: `<p>Der Designentwurf soll <strong>bis Mittwoch</strong> fertig sein. ${esc(b)} hat das zugesagt und schickt ihn als PDF.</p>`,
          cites: cite(7, 8),
        };
      case "budget":
        return {
          html: "<p>Beschlossen wurden <strong>12.000 Euro</strong> als Rahmen, inklusive Hosting für das erste Jahr. Neue Fotos kommen extra dazu, sie kosten weniger als 1.000 Euro.</p>",
          cites: cite(11, 12, 13),
        };
      case "hosting":
        return {
          html: `<p>${esc(a)} holt das Hosting-Angebot ein, am besten zwei Angebote zum Vergleich. Das Hosting für das erste Jahr ist im Budget von 12.000 Euro schon enthalten.</p>`,
          cites: cite(9, 11),
        };
      case "next":
        return {
          html: "<p>Das nächste Treffen ist am <strong>Donnerstag in einer Woche</strong>.</p>",
          cites: cite(15),
        };
      case "schedule":
        return {
          html: `<p>Der Zeitplan:</p><ul><li><strong>Mittwoch:</strong> Designentwurf als PDF (${esc(b)})</li><li><strong>Februar:</strong> Die Technik steht, danach zwei Wochen Tests</li><li><strong>Ende März:</strong> Die neue Website geht online</li></ul>`,
          cites: cite(3, 6, 7),
        };
      case "tasks":
        return {
          html: `<p>Diese Aufgaben wurden verteilt:</p><ul><li><strong>${esc(b)}:</strong> Designentwurf als PDF bis Mittwoch</li><li><strong>${esc(a)}:</strong> zwei Hosting-Angebote einholen</li><li><strong>${esc(a)}:</strong> die Kundin bis Freitag über den Zeitplan informieren</li></ul><p>Ich habe daraus eine Aufgabenliste vorbereitet.</p>`,
          cites: cite(7, 9, 15),
          action: {
            type: "task_draft",
            title: "Aufgabenliste aus dem Projektmeeting",
            prefix: "tasks",
            preview: `- [ ] Designentwurf als PDF schicken (${b}, bis Mittwoch)\n- [ ] Zwei Hosting-Angebote einholen (${a})\n- [ ] Kundin über den Zeitplan informieren (${a}, bis Freitag)`,
          },
        };
      case "email":
        return {
          html: "<p>Hier ist ein Entwurf für die E-Mail an die Kundin. Prüfen Sie ihn und speichern Sie ihn mit <strong>Confirm</strong> als Datei.</p>",
          cites: cite(3, 6, 7),
          action: {
            type: "email_draft",
            title: "E-Mail an die Kundin: Zeitplan der neuen Website",
            prefix: "email",
            preview:
              "Betreff: Zeitplan für Ihre neue Website\n\nGuten Tag,\n\nhier der aktuelle Stand aus unserem Projektmeeting:\n\n- Designentwurf (helle Variante): bis Mittwoch, als PDF\n- Technik: steht bis Februar, danach zwei Wochen Tests\n- Start der neuen Website: Ende März\n\nDas nächste Treffen ist am Donnerstag in einer Woche.\n\nViele Grüße",
          },
        };
      case "summarize":
        return {
          html: `<p><strong>Entscheidungen</strong></p><ul><li>Die Startseite wird in der <strong>hellen Variante</strong> weiterentwickelt.</li><li>Budget: <strong>12.000 Euro</strong> inklusive Hosting im ersten Jahr, neue Fotos kommen extra.</li><li>Ziel: Die neue Website geht <strong>Ende März</strong> online.</li></ul><p><strong>Nächste Schritte</strong></p><ul><li>Designentwurf als PDF bis Mittwoch (${esc(b)})</li><li>Zwei Hosting-Angebote einholen und die Kundin bis Freitag informieren (${esc(a)})</li><li>Nächstes Treffen: Donnerstag in einer Woche</li></ul>`,
          cites: cite(3, 5, 13),
        };
      case "keypoints":
        return {
          html: `<ul><li>Die neue Website soll <strong>Ende März</strong> online gehen.</li><li>Die <strong>helle Variante</strong> der Startseite wird weiterentwickelt.</li><li>Die Technik steht bis <strong>Februar</strong>, danach folgen zwei Wochen Tests.</li><li>${esc(b)} liefert den <strong>Designentwurf bis Mittwoch</strong> als PDF.</li><li>Das Budget liegt bei <strong>12.000 Euro</strong>, Fotos kommen extra.</li></ul>`,
          cites: cite(3, 5, 6, 7, 13),
        };
      case "speakers":
        return {
          html: `<ul><li><strong>${esc(k)}</strong> leitet das Meeting und verteilt die Aufgaben. Vorschlag: <em>Projektleitung</em>.</li><li><strong>${esc(a)}</strong> kümmert sich um Technik, Hosting und Zeitplan. Vorschlag: <em>Technik</em>.</li><li><strong>${esc(spk("SPEAKER_02"))}</strong> wird mit „Frau Brandt“ angesprochen und zeigt die Entwürfe. Vorschlag: <em>Frau Brandt (Design)</em>.</li></ul><p>Namen tragen Sie unter <strong>Edit transcript → Speakers</strong> ein.</p>`,
          cites: cite(0, 6, 7),
        };
      case "translate":
        return {
          html: `<p>Here is the transcript in English:</p><ul><li><strong>0:00 ${esc(k)}:</strong> Good morning, everyone. Let's start with the new website.</li><li><strong>0:05 ${esc(a)}:</strong> Sure. I brought the schedule.</li><li><strong>0:09 ${esc(spk("SPEAKER_02"))}:</strong> And I brought the first drafts.</li><li><strong>0:12 ${esc(k)}:</strong> Great. The goal is to launch the new site at the end of March. Today we'll settle the schedule, tasks and budget.</li></ul><p><em>(Im Demo gekürzt. In der App übersetzt Transcibio das ganze Transkript.)</em></p>`,
          cites: cite(0, 1, 2, 3),
        };
      case "app":
        return {
          html: `<p>Ich laufe vollständig auf diesem Rechner. Whisper (Modell <em>${profile}</em>) hat die Aufnahme abgeschrieben, pyannote hat die Sprecher erkannt, und ich antworte mit dem Sprachmodell <strong>${esc(S.settings.model)}</strong> über Ollama.</p><p>Aufnahme, Transkript und dieser Chat bleiben im Ordner <code>data/</code> auf Ihrem Rechner. Nichts davon wird ins Internet geschickt.</p>`,
          cites: [],
        };
      case "hello":
        return {
          html: "<p>Hallo! Fragen Sie mich etwas zum Meeting, zum Beispiel, welches Budget beschlossen wurde oder wer welche Aufgabe übernimmt.</p>",
          cites: [],
          suggest: true,
        };
      default:
        return {
          html: "<p>Dazu steht im Transkript nichts.</p><p><em>Hinweis: Diese Vorführung kennt nur das erfundene Meeting und einige vorbereitete Fragen. In der App beantwortet das Sprachmodell jede Frage.</em></p>",
          cites: [],
          suggest: true,
        };
    }
  }

  const SUGGESTIONS = ["Welches Budget wurde beschlossen?", "Wer übernimmt welche Aufgabe?", "Wann ist das nächste Treffen?"];

  const VOICE_TURNS = [
    {
      q: "Welches Budget wurde beschlossen?",
      de: "Beschlossen wurden 12.000 Euro als Rahmen, inklusive Hosting für das erste Jahr. Die neuen Fotos kommen extra dazu.",
      en: "The team agreed on a budget of 12,000 euros, including hosting for the first year. New photos come on top.",
      cites: [11, 13],
    },
    {
      q: "Und wer kümmert sich um das Hosting?",
      de: () => `Das übernimmt ${spk("SPEAKER_01")}. Er holt zwei Hosting-Angebote zum Vergleich ein.`,
      en: () => `${spk("SPEAKER_01")} takes care of it and will get two hosting offers to compare.`,
      cites: [9],
    },
  ];

  // ---------------------------------------------------------------- chat

  function sendChat(text, opts = {}) {
    const s = cur();
    if (!s || !text.trim() || chatBusy(s)) return;
    const user = { id: uid(), role: "user", text: text.trim() };
    const msg = { id: uid(), role: "assistant", status: "running" };
    s.messages.push(user, msg);
    S.draft = "";
    S.review = false;
    const reply = answer(text.trim());
    const think = S.settings.think;
    startJob(
      msg.id,
      [
        { label: "Searching the transcript…", from: 0, to: 20, ms: 650 },
        { label: "Found relevant passages", from: 20, to: 35, ms: 450 },
        { label: "Thinking…", from: 35, to: 80, ms: think ? 2600 : 1200 },
        { label: "Citing passages…", from: 80, to: 95, ms: 450 },
        { label: "Finalizing…", from: 95, to: 100, ms: 250 },
      ],
      () => {
        Object.assign(msg, reply, { status: "completed" });
        if (msg.action) {
          msg.action = { ...msg.action, id: uid(), status: "proposed" };
        }
        renderRegion("thread", { toBottom: true });
        renderRegion("composer");
        tourEvent("answered", { question: text.trim(), quick: opts.quick, action: !!msg.action });
        if (S.settings.tts && S.settings.ttsAuto && S.settings.ttsPlay) playTts(msg.id);
      },
    );
    renderRegion("thread", { toBottom: true });
    renderRegion("composer");
    tourRefresh();
  }

  function playTts(id) {
    const s = cur();
    const msg = s && s.messages.find((m) => m.id === id);
    if (!msg) return;
    S.ttsBusy = id;
    renderRegion("thread");
    later(() => {
      S.ttsBusy = null;
      renderRegion("thread");
      const holder = document.createElement("div");
      holder.innerHTML = msg.html || msg.text || "";
      if (!speak(holder.textContent || "", "de")) {
        toast("Im Demo liest Ihr Browser vor. Hier ist keine deutsche Stimme verfügbar (in der App spricht Piper).", "info");
      }
    }, 700);
  }

  // ---------------------------------------------------------------- transcription

  function transcribe(fromRecording) {
    const s = cur();
    if (!s) return;
    s.phase = "transcribing";
    s.diarized = S.settings.diarization;
    const stages = [
      { label: "Uploading…", from: 0, to: 8, ms: 700 },
      { label: "Transcribing audio…", from: 8, to: 60, ms: 2300 },
    ];
    if (s.diarized) stages.push({ label: "Identifying speakers…", from: 60, to: 85, ms: 1500 });
    stages.push(
      { label: "Aligning segments…", from: s.diarized ? 85 : 60, to: 96, ms: 700 },
      { label: "Saving transcript…", from: 96, to: 100, ms: 400 },
    );
    startJob(`tx-${s.id}`, stages, () => {
      s.phase = "ready";
      s.title = AUTO_TITLE;
      renderAll({ toBottom: true });
      toast("Transcript ready");
      tourEvent("transcribed");
    });
    renderAll({ toBottom: true });
    if (fromRecording) toast("Im Demo verwenden wir statt Ihrer Aufnahme das Beispielmeeting.", "info");
  }

  // ---------------------------------------------------------------- voice mode

  function stopVoice() {
    clearBucket(voiceTimers);
    hush();
    if (S && S.voice) S.voice = { on: false, phase: "idle", text: "", userSpeaking: false, turn: S.voice.turn };
  }

  function voiceTurn() {
    const s = cur();
    const turn = VOICE_TURNS[S.voice.turn];
    if (!s || !turn || !S.voice.on) return;
    const english = S.settings.voiceEngine === "kokoro";
    const vlater = (fn, ms) => later(fn, ms, voiceTimers);
    S.voice.userSpeaking = true;
    renderRegion("voice");
    vlater(() => {
      S.voice.userSpeaking = false;
      S.voice.phase = "transcribing";
      renderRegion("voice");
      vlater(() => {
        s.messages.push({ id: uid(), role: "user", text: turn.q });
        renderRegion("thread", { toBottom: true });
        const reply = typeof turn[english ? "en" : "de"] === "function" ? turn[english ? "en" : "de"]() : turn[english ? "en" : "de"];
        const words = reply.split(" ");
        S.voice.phase = "speaking";
        S.voice.text = "";
        renderRegion("voice");
        let spoken = speak(reply, english ? "en" : "de", null);
        let i = 0;
        const finish = () => {
          s.messages.push({
            id: uid(),
            role: "assistant",
            status: "completed",
            html: `<p>${esc(reply)}</p>`,
            cites: turn.cites,
          });
          S.voice.phase = "listening";
          S.voice.text = "";
          S.voice.turn += 1;
          renderRegion("thread", { toBottom: true });
          renderRegion("voice");
          tourEvent("voiceAnswered");
          if (S.voice.turn < VOICE_TURNS.length) vlater(voiceTurn, 2600);
        };
        const stream = () => {
          if (!S.voice.on) return;
          i += 1;
          S.voice.text = words.slice(0, i).join(" ");
          renderRegion("voice");
          if (i < words.length) {
            vlater(stream, 260);
          } else if (spoken && synth && synth.speaking) {
            const wait = () => (synth.speaking ? vlater(wait, 200) : finish());
            vlater(wait, 200);
            spoken = false;
          } else {
            vlater(finish, 500);
          }
        };
        vlater(stream, 300);
      }, 900);
    }, 1900);
  }

  function toggleVoice() {
    if (S.voice.on) {
      stopVoice();
      renderRegion("voice");
      renderRegion("composer");
      return;
    }
    const s = cur();
    if (!s) return;
    S.voice = { on: true, phase: "starting", text: "", userSpeaking: false, turn: S.voice.turn >= VOICE_TURNS.length ? 0 : S.voice.turn };
    renderRegion("voice");
    renderRegion("composer");
    later(
      () => {
        if (!S.voice.on) return;
        S.voice.phase = "listening";
        renderRegion("voice");
        if (s.phase === "ready") later(voiceTurn, 1300, voiceTimers);
      },
      800,
      voiceTimers,
    );
  }

  // ---------------------------------------------------------------- rendering

  function fade(id) {
    if (seen.has(id)) return "";
    seen.add(id);
    return " a-fade";
  }

  function renderSidebar() {
    if (S.collapsed) {
      return `<aside class="a-rail">
        <button class="a-btn is-ghost is-icon" data-act="toggle-side" aria-label="Expand sidebar" title="Expand sidebar">${ic("panelLeft")}</button>
        <button class="a-btn is-ghost is-icon" data-act="new-session" data-tour="new-session" aria-label="New session" title="New session">${ic("plus")}</button>
        <div class="a-spacer"></div>
        <button class="a-btn is-ghost is-icon" data-act="open-settings" data-tour="settings" aria-label="Settings" title="Settings">${ic("settings")}</button>
      </aside>`;
    }
    const themeMenu =
      S.menu === "theme"
        ? `<div class="a-menu is-up-right" role="menu">
            <button class="a-menu-item" data-act="theme" data-value="light">${ic("sun")}<span>Light</span></button>
            <button class="a-menu-item" data-act="theme" data-value="dark">${ic("moon")}<span>Dark</span></button>
            <button class="a-menu-item" data-act="theme" data-value="system">${ic("monitor")}<span>System</span></button>
          </div>`
        : "";
    return `<aside class="a-side">
      <div class="a-side-top">
        <span class="a-side-name">Transcibio</span>
        <button class="a-btn is-ghost is-icon" data-act="toggle-side" aria-label="Collapse sidebar" title="Collapse sidebar">${ic("panelLeft")}</button>
      </div>
      <div class="a-side-tools">
        <button class="a-btn is-secondary is-full" data-act="new-session" data-tour="new-session">${ic("plus")}<span>New session</span></button>
        <label class="a-search">${ic("search")}<input type="text" data-input="query" placeholder="Search sessions" value="${esc(S.query)}" aria-label="Search sessions"></label>
      </div>
      <div class="a-list" data-region="list">${renderList()}</div>
      <div class="a-side-foot">
        <button class="a-btn is-ghost" data-act="open-settings" data-tour="settings">${ic("settings")}<span>Settings</span></button>
        <div style="position:relative">
          <button class="a-btn is-ghost is-icon" data-act="theme-menu" aria-label="Theme" title="Theme">${ic(S.dark ? "moon" : "sun")}</button>
          ${themeMenu}
        </div>
      </div>
    </aside>`;
  }

  function renderList() {
    const q = S.query.trim().toLowerCase();
    const list = S.sessions.filter((s) => !q || s.title.toLowerCase().includes(q));
    if (!list.length) return '<p class="a-muted a-xs" style="padding:8px 6px;margin:0">No sessions yet</p>';
    return list
      .map(
        (s) => `<div class="a-item${s.id === S.currentId ? " is-selected" : ""}">
          <button class="a-item-btn" data-act="select" data-id="${s.id}">${esc(s.title || "Untitled")}</button>
          <button class="a-item-more" data-act="more" aria-label="More">${ic("more")}</button>
        </div>`,
      )
      .join("");
  }

  function renderHeader() {
    const s = cur();
    return `<header class="a-header">
      <h4>${s ? esc(s.title || "Untitled session") : "Transcibio"}</h4>
      ${s ? `<button class="a-btn is-ghost is-sm" data-act="open-session-sheet">${ic("info")}<span>Session details</span></button>` : ""}
    </header>`;
  }

  function renderEmpty(variant) {
    if (variant === "no-session") {
      return `<div class="a-empty">
        <div class="a-empty-icon">${ic("message")}</div>
        <h5>Start a new session</h5>
        <p>Create a session to transcribe audio and chat with it.</p>
        <button class="a-link" data-act="new-session">New session</button>
      </div>`;
    }
    return `<div class="a-empty">
      <div class="a-empty-icon">${ic("upload")}</div>
      <h5>Upload audio to get started</h5>
      <p>Drop a .mp3 or .wav into the composer, or use the + button.</p>
      <button class="a-link" data-act="attach">Attach audio</button>
    </div>`;
  }

  function renderJobCard(s) {
    const id = `tx-${s.id}`;
    const job = jobs.get(id);
    if (!job) return "";
    const pct = jobPct(job);
    return `<div class="a-card a-job${fade(id)}" data-job="${id}">
      <div class="a-job-row">${ic("loader", "a-spin")}<span class="a-strong j-label">${jobStage(job).label}</span>
        <span class="a-job-meta"><span data-elapsed-start="${job.start}">${fmt(Date.now() - job.start)}</span><span class="j-pct">${pct}%</span></span>
      </div>
      <div class="a-progress"><span class="j-bar" style="width:${pct}%"></span></div>
    </div>`;
  }

  function renderTranscript(s) {
    const open = s.transcriptOpen;
    const busy = chatBusy(s);
    const p = s.player;
    const t = playerTime(s);
    const segs = open
      ? `<div class="a-segs">${s.segs
          .map(
            (seg) => `<div class="a-seg"><span class="a-seg-time">${fmtS(seg.s)}</span><div>${
              s.diarized ? `<span class="a-seg-spk">${esc(spk(seg.spk))}: </span>` : ""
            }<span>${esc(seg.text)}</span></div></div>`,
          )
          .join("")}</div>`
      : "";
    return `<div class="a-card${fade(`tb-${s.id}`)}">
      <div class="a-card-row">
        <button class="a-collapse-btn${open ? " is-open" : ""}" data-act="toggle-transcript" data-tour="transcript-toggle" aria-expanded="${open}">
          ${ic("chevronDown")}<span class="a-strong">Transcript</span>
          <span class="a-muted a-xs">· ${s.segs.length} segments · ${s.diarized ? SPEAKER_KEYS.length : 0} speakers</span>
        </button>
        <button class="a-btn is-outline is-sm" data-act="open-transcript-sheet" data-tour="edit-transcript">${ic("pencil")}<span>Edit transcript</span></button>
      </div>
      <div class="a-player" data-player="${s.id}">
        <button class="a-btn is-ghost is-xs-icon" data-act="player-toggle" aria-label="${p.playing ? "Pause" : "Play"}">${ic(p.playing ? "pause" : "play")}</button>
        <div class="a-player-track" data-act="player-seek"><span class="p-bar" style="width:${(t / FILE.seconds) * 100}%"></span></div>
        <span class="a-mono a-xs a-muted p-time">${fmtS(t)} / ${fmtS(FILE.seconds)}</span>
      </div>
      ${segs}
      <div class="a-quick">${QUICK.map(
        ([key, label]) =>
          `<button class="a-btn is-outline is-sm" data-act="quick" data-key="${key}" data-tour="qa-${key}"${busy ? " disabled" : ""}>${label}</button>`,
      ).join("")}</div>
    </div>`;
  }

  function renderMessage(s, m) {
    if (m.role === "user") {
      return `<article class="a-msg${fade(m.id)}"><div class="a-avatar">U</div><div class="a-msg-body">
        <div class="a-msg-role">You</div><div class="a-prose" style="white-space:pre-wrap">${esc(m.text)}</div></div></article>`;
    }
    let body = "";
    if (m.status === "running") {
      const job = jobs.get(m.id);
      const pct = job ? jobPct(job) : 0;
      body = `<div data-job="${m.id}">
        <div class="a-stage">${ic("loader", "a-spin")}<span class="j-label">${job ? jobStage(job).label : "Generating response…"}</span>
          <span class="a-mono"><span data-elapsed-start="${job ? job.start : Date.now()}">0:00</span> · <span class="j-pct">${pct}%</span></span></div>
        <div class="a-mini-progress"><span class="j-bar" style="width:${pct}%"></span></div>
      </div>`;
    } else {
      body = `<div class="a-prose">${m.html}</div>`;
      if (m.suggest) {
        body += `<div class="a-row" style="flex-wrap:wrap">${SUGGESTIONS.map(
          (q) => `<button class="a-btn is-outline is-sm" data-act="ask" data-q="${esc(q)}">${esc(q)}</button>`,
        ).join("")}</div>`;
      }
      if (m.cites && m.cites.length) {
        body += `<div class="a-cites">${m.cites
          .map((i) => {
            const seg = s.segs[i];
            return `<div class="a-cite">${ic("quote")}<div>${
              S.settings.timestamps ? `<span class="a-cite-time">${fmtS(seg.s)} – ${fmtS(seg.e)}</span>` : ""
            }<p style="margin:0">${esc(seg.text)}</p></div></div>`;
          })
          .join("")}</div>`;
      }
      if (m.action) body += renderAction(m);
      if (S.settings.tts) {
        const busy = S.ttsBusy === m.id;
        body += `<div class="a-row"><button class="a-btn is-outline is-sm" data-act="tts" data-msg="${m.id}"${busy ? " disabled" : ""}>${
          busy ? ic("loader", "a-spin") : ic("volume")
        }<span>${busy ? "Generating…" : "Play"}</span></button></div>`;
      }
    }
    return `<article class="a-msg is-assistant${fade(m.id)}"><div class="a-avatar">P</div><div class="a-msg-body">
      <div class="a-msg-role">Assistant</div>${body}</div></article>`;
  }

  function renderAction(m) {
    const a = m.action;
    const badge = { completed: "is-success", confirmed: "is-default", executing: "is-default" }[a.status] || "";
    const files = a.prefix === "email" ? ["md", "json", "eml"] : ["md", "json"];
    return `<div class="a-action">
      <div class="a-action-title">${ic("fileText")}<span>${esc(a.title)}</span></div>
      <div class="a-action-meta"><span class="a-mono">${a.type}</span><span class="a-badge ${badge}">${a.status}</span></div>
      <pre class="a-pre">${esc(a.preview)}</pre>
      ${
        a.status === "completed"
          ? `<ul class="a-artifacts">${files
              .map(
                (ext) =>
                  `<li><button data-act="download" data-msg="${m.id}" data-ext="${ext}">${ic("download")}<span>${a.prefix}_${a.id}.${ext}</span></button></li>`,
              )
              .join("")}</ul>`
          : ""
      }
      ${
        a.status === "proposed"
          ? `<div class="a-row">
              <button class="a-btn is-primary is-sm" data-act="confirm-action" data-msg="${m.id}" data-tour="confirm-action">${ic("check")}<span>Confirm</span></button>
              <button class="a-btn is-ghost is-sm" data-act="cancel-action" data-msg="${m.id}">${ic("x")}<span>Cancel</span></button>
            </div>`
          : ""
      }
    </div>`;
  }

  function renderThread() {
    if (S.sessions.find((s) => s.id === S.currentId && s.example)) {
      return renderEmpty("no-session");
    }
    const s = cur();
    if (!s) return renderEmpty("no-session");
    const hasContent = s.phase === "ready" || jobs.has(`tx-${s.id}`) || s.messages.length > 0;
    if (!hasContent) return renderEmpty("no-audio");
    return `<div class="a-thread-inner">
      ${s.phase === "ready" ? renderTranscript(s) : ""}
      ${s.phase === "transcribing" ? renderJobCard(s) : ""}
      ${s.messages.map((m) => renderMessage(s, m)).join("")}
    </div>`;
  }

  function renderVoice() {
    const s = cur();
    if (!s) return "";
    const v = S.voice;
    const engine = S.settings.voiceEngine === "kokoro" ? "Kokoro · English" : "Piper · Deutsch";
    let status;
    if (!v.on) status = "<span>Freihändiges Gespräch — einschalten und einfach sprechen.</span>";
    else if (v.phase === "speaking")
      status = `${ic("volume", "is-primary")}<span>${esc(v.text) || "Spricht…"}</span>`;
    else if (v.phase === "listening")
      status = `${ic("mic", "is-primary")}<span>Zuhören… sprechen Sie einfach los.</span>${
        v.userSpeaking ? '<span class="a-level" aria-hidden="true"><i></i><i></i><i></i><i></i></span>' : ""
      }`;
    else status = `${ic("loader", "a-spin")}<span>${v.phase === "transcribing" ? "Erkenne Sprache…" : "Startet…"}</span>`;
    return `<div class="a-voicebar">
      <button class="a-voice-toggle${v.on ? " is-on" : ""}" data-act="voice-toggle" data-tour="voice-toggle" aria-pressed="${v.on}">${ic("volume")}Sprachmodus</button>
      ${v.on ? `<span class="a-xs a-muted">${engine}</span>` : ""}
      <div class="a-voice-status" aria-live="polite">${status}</div>
    </div>`;
  }

  function renderComposer() {
    const s = cur();
    if (!s) return "";
    const recording = s.phase === "recording";
    const busy = chatBusy(s);
    const cmd = S.command.state;
    const disabled = cmd !== "idle" || busy;
    const canSend = !disabled && S.draft.trim().length > 0;
    const maxSuffix = S.settings.engine === "nemotron" ? " / 60:00" : "";
    const attach = recording
      ? `<button class="a-btn is-destructive" data-act="stop-recording" data-tour="stop-recording" aria-label="Stop recording">${ic("square")}<span class="a-mono a-xs"><span data-elapsed-start="${s.recStart}">0:00</span>${maxSuffix}</span></button>`
      : `<button class="a-btn is-ghost is-icon" data-act="attach" data-tour="attach" aria-label="Attach audio" title="Attach audio"${disabled ? " disabled" : ""}>${ic("plus")}</button>`;
    const menu =
      S.menu === "attach"
        ? `<div class="a-menu" role="menu">
            <button class="a-menu-item" data-act="upload" data-tour="upload">${ic("fileAudio")}<span>Upload meeting audio</span></button>
            <button class="a-menu-item" data-act="record" data-tour="record">${ic("disc")}<span>Record meeting</span></button>
          </div>`
        : "";
    const mic =
      cmd === "recording"
        ? `<button class="a-btn is-destructive" data-act="mic" aria-label="Stop recording">${ic("square")}<span class="a-mono a-xs" data-elapsed-start="${S.command.start}">0:00</span></button>`
        : `<button class="a-btn is-ghost is-icon" data-act="mic" aria-label="Start voice command" title="Voice command"${
            cmd === "uploading" || (S.voice.on && cmd === "idle") || busy ? " disabled" : ""
          }>${ic("mic")}</button>`;
    const review = S.review
      ? `<div class="a-review">${ic("mic")}<div style="flex:1"><p class="a-strong">Voice command ready</p><p class="a-xs a-muted">Review and edit, then send.</p></div>
          <button class="a-btn is-ghost is-xs-icon" data-act="review-dismiss" aria-label="Discard">${ic("x")}</button></div>`
      : "";
    return `<div class="a-composer-wrap">${review}
      <div class="a-composer"${disabled ? ' style="opacity:.6"' : ""}>
        ${attach}${menu}
        <textarea rows="1" data-input="draft" placeholder="Ask about your meeting or transcript…" aria-label="Message"${disabled ? " disabled" : ""}>${esc(S.draft)}</textarea>
        ${mic}
        <button class="a-btn is-primary is-icon" data-act="send" data-tour="send" aria-label="Send message"${canSend ? "" : " disabled"}>${
          busy ? ic("loader", "a-spin") : ic("arrowUp")
        }</button>
      </div>
    </div>`;
  }

  function settingLabel(text, tip) {
    return `<span class="a-label">${text}<span class="a-help" title="${esc(tip)}" aria-label="${esc(tip)}">${ic("help")}</span></span>`;
  }
  function select(key, options, label) {
    const d = S.draftSettings;
    return `<select class="a-select" data-setting="${key}" aria-label="${label}">${options
      .map(([v, l]) => `<option value="${v}"${d[key] === v ? " selected" : ""}>${l}</option>`)
      .join("")}</select>`;
  }
  function sw(key, label, disabled = false) {
    const d = S.draftSettings;
    return `<button class="a-switch" role="switch" aria-checked="${d[key]}" aria-label="${label}" data-act="setting-toggle" data-key="${key}"${disabled ? " disabled" : ""}></button>`;
  }

  function renderSettings() {
    const d = S.draftSettings;
    const engineBlock =
      d.engine === "whisper-pyannote"
        ? `<div class="a-field">${settingLabel("Whisper model", "Larger models are more accurate but slower.")}
            ${select("profile", [["fast", "Fast (small)"], ["balanced", "Balanced (medium)"], ["quality", "Quality (large-v3)"]], "Whisper model")}
            <p class="a-hint">No length limit for recordings and uploads.</p></div>`
        : `<div class="a-note-box">
            <p><span class="a-muted">Model: </span>nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-NVFP4</p>
            <p class="a-muted">Transcribes recordings and uploads up to 60 minutes each. For longer audio, use Whisper.</p>
            <p class="a-muted">Also used for voice input (voice commands and voice mode).</p>
            <p class="a-ok">Server is running.</p></div>`;
    return `<div class="a-overlay" data-act="close-overlay"></div>
      <div class="a-dialog" role="dialog" aria-modal="true" aria-label="Settings">
        <button class="a-close" data-act="close-overlay" aria-label="Close">${ic("x")}</button>
        <h5>Settings</h5>
        <p class="a-dialog-desc">Configure transcription, chat, and speech.</p>
        <div class="a-box"><span class="a-box-title">Transcription</span>
          <div class="a-field">${settingLabel("Engine", "Used for uploads, recordings and voice input (voice commands and voice mode). Nemotron 3.5 Transcribe is an optional second engine and needs its own server.")}
            ${select("engine", [["whisper-pyannote", "Whisper + pyannote"], ["nemotron", "Nemotron 3.5 Transcribe"]], "Transcription engine")}</div>
          ${engineBlock}
          <div class="a-switch-row">${settingLabel("Speaker diarization", d.engine === "nemotron" ? "Labels who said what. Nemotron detects the speakers itself." : "Labels who said what, with pyannote. Requires a Hugging Face token.")}${sw("diarization", "Speaker diarization")}</div>
        </div>
        <div class="a-box"><span class="a-box-title">Chat</span>
          <div class="a-field">${settingLabel("Model", "The language model used for chat answers and transcript corrections.")}
            ${select("model", [["gemma4:e4b", "gemma4:e4b"], ["gemma4:26b", "gemma4:26b"]], "Chat model")}</div>
          <div class="a-field"><div class="a-switch-row">${settingLabel("Thinking mode", "The model thinks before it answers typed questions and transcript corrections: better answers to harder questions, but slower. Voice mode never thinks, so it can answer quickly.")}${sw("think", "Thinking mode")}</div>
            <p class="a-hint">${d.think ? "On: better answers to harder questions, but slower." : "Off: faster answers."}</p></div>
          <div class="a-field">${settingLabel("Response detail", "How detailed the AI responses should be.")}
            ${select("detail", [["brief", "Brief"], ["normal", "Normal"], ["detailed", "Detailed"]], "Response detail")}</div>
          <div class="a-switch-row">${settingLabel("Show citation timestamps", "Display timestamps in transcript citations within chat.")}${sw("timestamps", "Show citation timestamps")}</div>
        </div>
        <div class="a-box"><span class="a-box-title">Voice</span>
          <div class="a-field">${settingLabel("Voice command default", "Whether to review transcribed voice commands before sending them.")}
            ${select("sendMode", [["review_then_send", "Review then send"], ["auto_send", "Auto-send"]], "Voice command default")}</div>
          <div class="a-field">${settingLabel("Voice-mode engine", "Streaming voice mode: Piper speaks German; Kokoro speaks English.")}
            ${select("voiceEngine", [["piper", "Piper — Deutsch"], ["kokoro", "Kokoro — English"]], "Voice-mode engine")}</div>
          <div class="a-switch-row">${settingLabel("TTS enabled", "Enable text-to-speech audio playback of AI responses.")}${sw("tts", "TTS enabled")}</div>
          <div class="a-switch-row">${settingLabel("Auto-generate on reply", "Automatically generate speech when the AI replies.")}${sw("ttsAuto", "Auto-generate on reply", !d.tts)}</div>
          <div class="a-switch-row">${settingLabel("Auto-play audio", "Automatically play generated speech audio.")}${sw("ttsPlay", "Auto-play audio", !d.tts)}</div>
        </div>
        <div class="a-box is-danger"><span class="a-box-title">Danger zone</span>
          <p class="a-hint">Delete every session, its transcripts, chat history, and audio files. This cannot be undone.</p>
          <div>${
            S.confirmDelete
              ? `<button class="a-btn is-destructive is-sm" data-act="delete-all">Confirm delete all</button> <button class="a-btn is-ghost is-sm" data-act="delete-cancel">Cancel</button>`
              : `<button class="a-btn is-destructive is-sm" data-act="delete-ask">Delete all sessions</button>`
          }</div>
        </div>
        <div class="a-dialog-foot">
          <button class="a-btn is-ghost" data-act="close-overlay">Cancel</button>
          <button class="a-btn is-primary" data-act="save-settings">Save</button>
        </div>
      </div>`;
  }

  function renderTranscriptSheet() {
    const s = cur();
    if (!s) return "";
    const tab = S.sheetTab;
    const segments = s.segs
      .map((seg, i) => {
        const editing = S.editingSeg === i;
        return `<div class="a-seg-card">
          <div class="a-seg-card-head"><span class="a-mono">${fmtS(seg.s)} – ${fmtS(seg.e)}</span>${s.diarized ? `<b>${esc(spk(seg.spk))}</b>` : ""}</div>
          ${
            editing
              ? `<div style="margin-top:8px;display:grid;gap:8px"><textarea class="a-input" style="height:auto;padding:8px 10px" rows="3" data-input="seg">${esc(S.segDraft)}</textarea>
                  <div style="display:flex;gap:8px"><button class="a-btn is-primary is-sm" data-act="seg-save">${ic("save")}<span>Save</span></button><button class="a-btn is-ghost is-sm" data-act="seg-cancel">${ic("x")}<span>Cancel</span></button></div></div>`
              : `<div class="a-seg-card-body"><p>${esc(seg.text)}</p><button class="a-btn is-ghost is-sm" data-act="seg-edit" data-i="${i}" aria-label="Edit segment">${ic("pencil")}</button></div>`
          }
        </div>`;
      })
      .join("");
    const speakers = SPEAKER_KEYS.map((key) => {
      if (S.editingSpeaker === key) {
        return `<div class="a-spk"><input class="a-input" data-input="speaker" value="${esc(S.speakerDraft)}" aria-label="Speaker name">
          <button class="a-btn is-primary is-sm" data-act="spk-save" data-tour="save-spk" aria-label="Save"${S.speakerDraft.trim() ? "" : " disabled"}>${ic("save")}</button>
          <button class="a-btn is-ghost is-sm" data-act="spk-cancel" aria-label="Cancel">${ic("x")}</button></div>`;
      }
      return `<div class="a-spk"><div style="flex:1"><div class="a-spk-name">${esc(spk(key))}</div><div class="a-xs a-muted">${key}</div></div>
        <button class="a-btn is-ghost is-sm" data-act="spk-edit" data-key="${key}" data-tour="edit-spk-${key}" aria-label="Rename ${key}">${ic("pencil")}</button></div>`;
    }).join("");
    return `<div class="a-overlay" data-act="close-overlay"></div>
      <div class="a-sheet" role="dialog" aria-modal="true" aria-label="Edit transcript">
        <button class="a-close" data-act="close-overlay" aria-label="Close">${ic("x")}</button>
        <h5>Edit transcript</h5>
        <p class="a-dialog-desc" style="margin-bottom:0">Revision ${s.revision} · ${s.revision > 1 ? "edited" : "transcription"}</p>
        <div class="a-tabs" role="tablist">
          <button role="tab" aria-selected="${tab === "segments"}" data-act="sheet-tab" data-tab="segments">Segments</button>
          <button role="tab" aria-selected="${tab === "speakers"}" data-act="sheet-tab" data-tab="speakers" data-tour="tab-speakers">Speakers</button>
        </div>
        <div>${tab === "segments" ? segments : s.diarized ? speakers : '<p class="a-hint">No speakers: speaker diarization was off for this transcript.</p>'}</div>
      </div>`;
  }

  function renderSessionSheet() {
    const s = cur();
    if (!s) return "";
    const hasAudio = s.phase === "ready" || s.phase === "transcribing";
    const job = jobs.get(`tx-${s.id}`);
    return `<div class="a-overlay" data-act="close-overlay"></div>
      <div class="a-sheet is-narrow" role="dialog" aria-modal="true" aria-label="Session details">
        <button class="a-close" data-act="close-overlay" aria-label="Close">${ic("x")}</button>
        <h5>Session details</h5>
        <p class="a-dialog-desc">${esc(s.title)}</p>
        <div class="a-section-title">Meeting audio</div>
        <div style="display:grid;gap:8px">
          <button class="a-btn is-outline is-full" data-act="upload">${ic("fileAudio")}<span>Upload audio file</span></button>
          <button class="a-btn is-outline is-full" data-act="${s.phase === "recording" ? "stop-recording" : "record"}">${ic("disc")}<span>${s.phase === "recording" ? "Stop recording" : "Record meeting"}</span></button>
        </div>
        ${
          hasAudio
            ? `<dl class="a-dl"><div><dt>File</dt><dd class="a-mono">${FILE.name}</dd></div><div><dt>Duration</dt><dd>${fmtS(FILE.seconds)}</dd></div><div><dt>Type</dt><dd>${FILE.mime}</dd></div></dl>`
            : ""
        }
        ${
          hasAudio
            ? `<div class="a-section-title">Transcription</div>
              <div class="a-card" style="margin:0;padding:12px"${job ? ` data-job="tx-${s.id}"` : ""}>
                <div class="a-job-row">${job ? ic("loader", "a-spin") : ""}<span>${job ? "running" : "succeeded"}</span><span class="a-job-meta"><span class="j-pct">${job ? jobPct(job) : 100}%</span></span></div>
                <div class="a-progress"><span class="j-bar" style="width:${job ? jobPct(job) : 100}%"></span></div>
              </div>`
            : ""
        }
      </div>`;
  }

  function renderOverlay() {
    if (S.overlay === "settings") return renderSettings();
    if (S.overlay === "transcript") return renderTranscriptSheet();
    if (S.overlay === "session") return renderSessionSheet();
    return "";
  }

  function renderToast() {
    if (!S.toast) return "";
    return `<div class="a-toast${S.toast.kind === "info" ? " is-info" : ""}" role="status">${ic(
      S.toast.kind === "info" ? "info" : "checkCircle",
    )}<span>${esc(S.toast.text)}</span></div>`;
  }

  const RENDER = {
    sidebar: renderSidebar,
    header: renderHeader,
    thread: renderThread,
    voice: renderVoice,
    composer: renderComposer,
    overlay: renderOverlay,
    toast: renderToast,
    list: renderList,
  };

  function mount() {
    root.innerHTML = `<div class="a-root" data-a-root>
      <div class="a-shell">
        <div data-region="sidebar" style="display:contents"></div>
        <main class="a-main">
          <div data-region="header"></div>
          <div class="a-thread" data-region="thread"></div>
          <div data-region="voice"></div>
          <div data-region="composer"></div>
        </main>
      </div>
      <div data-region="overlay"></div>
      <div data-region="toast"></div>
      <div class="tour-pointer" data-tour-pointer hidden aria-hidden="true">${ic("pointer")}<span>Hier klicken</span></div>
    </div>`;
  }

  function renderRegion(name, opts = {}) {
    const el = root.querySelector(`[data-region="${name}"]`);
    if (!el) return;
    const active = document.activeElement;
    const focusKey = active && el.contains(active) ? active.dataset.input : null;
    const sel = focusKey ? [active.selectionStart, active.selectionEnd] : null;
    const scroller = name === "thread" ? el : el.querySelector(".a-dialog, .a-sheet, .a-list");
    const scrollTop = scroller ? scroller.scrollTop : 0;
    el.innerHTML = RENDER[name]();
    if (name === "thread") {
      el.scrollTop = opts.toBottom ? el.scrollHeight : scrollTop;
    } else {
      const again = el.querySelector(".a-dialog, .a-sheet, .a-list");
      if (again && !opts.resetScroll) again.scrollTop = scrollTop;
    }
    if (focusKey) {
      const input = el.querySelector(`[data-input="${focusKey}"]`);
      if (input) {
        input.focus();
        if (sel && input.setSelectionRange) input.setSelectionRange(sel[0], sel[1]);
      }
    }
    if (name === "composer") growTextarea();
    highlight();
  }

  function renderAll(opts = {}) {
    root.querySelector("[data-a-root]").classList.toggle("dark", S.dark);
    ["sidebar", "header", "thread", "voice", "composer", "overlay", "toast"].forEach((r) =>
      renderRegion(r, r === "thread" ? opts : {}),
    );
    renderTour();
  }

  function growTextarea() {
    const ta = root.querySelector('[data-input="draft"]');
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
  }

  let toastTimer = 0;
  function toast(text, kind = "success") {
    S.toast = { text, kind };
    renderRegion("toast");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      S.toast = null;
      renderRegion("toast");
    }, 3600);
  }

  // Live values (elapsed time, progress, audio player) without re-rendering.
  function playerTime(s) {
    const p = s.player;
    if (!p.playing) return p.t;
    return Math.min(FILE.seconds, p.t + (Date.now() - p.since) / 1000);
  }
  function tick() {
    const now = Date.now();
    root.querySelectorAll("[data-elapsed-start]").forEach((el) => {
      el.textContent = fmt(now - Number(el.dataset.elapsedStart));
    });
    root.querySelectorAll("[data-job]").forEach((el) => {
      const job = jobs.get(el.dataset.job);
      if (!job) return;
      const pct = jobPct(job);
      const label = el.querySelector(".j-label");
      if (label && label.textContent !== jobStage(job).label) label.textContent = jobStage(job).label;
      el.querySelectorAll(".j-pct").forEach((p) => (p.textContent = `${pct}%`));
      el.querySelectorAll(".j-bar").forEach((b) => (b.style.width = `${pct}%`));
    });
    const s = cur();
    if (s && s.player.playing) {
      const t = playerTime(s);
      if (t >= FILE.seconds) {
        s.player = { playing: false, t: 0, since: 0 };
        renderRegion("thread");
        return;
      }
      const el = root.querySelector(`[data-player="${s.id}"]`);
      if (el) {
        el.querySelector(".p-bar").style.width = `${(t / FILE.seconds) * 100}%`;
        el.querySelector(".p-time").textContent = `${fmtS(t)} / ${fmtS(FILE.seconds)}`;
      }
    }
    if (S.command.state === "recording" && now - S.command.start > 4000) stopCommand();
  }

  // ---------------------------------------------------------------- actions

  function download(msgId, ext) {
    const s = cur();
    const msg = s && s.messages.find((m) => m.id === msgId);
    if (!msg || !msg.action) return;
    const a = msg.action;
    let content = a.preview;
    let type = "text/markdown";
    if (ext === "json") {
      type = "application/json";
      content = JSON.stringify(
        a.prefix === "email"
          ? { action_id: a.id, type: a.type, subject: "Zeitplan für Ihre neue Website", body: a.preview.split("\n\n").slice(1).join("\n\n") }
          : { action_id: a.id, type: a.type, tasks: a.preview.split("\n").map((l) => l.replace(/^- \[ \] /, "")) },
        null,
        2,
      );
    } else if (ext === "eml") {
      type = "message/rfc822";
      content = `Subject: Zeitplan für Ihre neue Website\nContent-Type: text/plain; charset=utf-8\n\n${a.preview.split("\n\n").slice(1).join("\n\n")}\n`;
    }
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${a.prefix}_${a.id}.${ext}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function startCommand() {
    S.command = { state: "recording", start: Date.now() };
    renderRegion("composer");
  }
  function stopCommand() {
    if (S.command.state !== "recording") return;
    S.command = { state: "uploading", start: 0 };
    renderRegion("composer");
    later(() => {
      S.command = { state: "idle", start: 0 };
      const text = "Wer kümmert sich um das Hosting?";
      if (S.settings.sendMode === "auto_send") {
        renderRegion("composer");
        sendChat(text);
      } else {
        S.draft = text;
        S.review = true;
        renderRegion("composer");
        toast("Im Demo ist die gesprochene Frage vorbereitet.", "info");
      }
    }, 800);
  }

  const ACTIONS = {
    "toggle-side": () => {
      S.collapsed = !S.collapsed;
      S.menu = null;
      renderRegion("sidebar");
    },
    "new-session": () => {
      newSession();
      S.menu = null;
      S.overlay = null;
      if (narrow()) S.collapsed = true;
      renderAll();
      tourEvent("sessionCreated");
    },
    select: (el) => {
      const s = S.sessions.find((x) => x.id === el.dataset.id);
      if (!s) return;
      if (s.example) {
        toast("Beispiel: Diese Sitzung ist im Demo nur zur Ansicht da.", "info");
        return;
      }
      stopVoice();
      S.currentId = s.id;
      S.draft = "";
      S.review = false;
      renderAll({ toBottom: true });
    },
    more: () => toast("Umbenennen und Löschen sind im Demo ausgeschaltet.", "info"),
    "theme-menu": () => {
      S.menu = S.menu === "theme" ? null : "theme";
      renderRegion("sidebar");
    },
    theme: (el) => {
      const v = el.dataset.value;
      S.dark = v === "dark" || (v === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
      S.menu = null;
      root.querySelector("[data-a-root]").classList.toggle("dark", S.dark);
      renderRegion("sidebar");
    },
    attach: () => {
      if (!cur()) return;
      S.menu = S.menu === "attach" ? null : "attach";
      renderRegion("composer");
      tourRefresh();
    },
    upload: () => {
      const s = cur();
      if (!s) return;
      S.menu = null;
      S.overlay = null;
      s.messages = s.phase === "ready" ? s.messages : [];
      s.transcriptOpen = false;
      transcribe(false);
      renderRegion("overlay");
      tourEvent("uploaded");
    },
    record: () => {
      const s = cur();
      if (!s) return;
      S.menu = null;
      S.overlay = null;
      s.phase = "recording";
      s.recStart = Date.now();
      renderAll();
      toast("Im Demo wird nichts aufgenommen. Klicken Sie auf Stopp, wann Sie möchten.", "info");
      tourEvent("uploaded");
    },
    "stop-recording": () => {
      S.overlay = null;
      renderRegion("overlay");
      transcribe(true);
    },
    "toggle-transcript": () => {
      const s = cur();
      s.transcriptOpen = !s.transcriptOpen;
      renderRegion("thread");
      if (s.transcriptOpen) tourEvent("transcriptOpened");
    },
    "open-transcript-sheet": () => {
      S.overlay = "transcript";
      S.sheetTab = "segments";
      S.editingSpeaker = null;
      S.editingSeg = null;
      renderRegion("overlay", { resetScroll: true });
      tourRefresh();
    },
    "open-session-sheet": () => {
      S.overlay = "session";
      renderRegion("overlay", { resetScroll: true });
    },
    "sheet-tab": (el) => {
      S.sheetTab = el.dataset.tab;
      renderRegion("overlay", { resetScroll: true });
      tourRefresh();
    },
    "spk-edit": (el) => {
      S.editingSpeaker = el.dataset.key;
      const suggested = tour.active && currentStep().id === "rename" && el.dataset.key === "SPEAKER_00" && !renamed("SPEAKER_00");
      S.speakerDraft = suggested ? "Frau Keller" : spk(el.dataset.key);
      renderRegion("overlay");
      root.querySelector('[data-input="speaker"]')?.focus();
      tourRefresh();
    },
    "spk-cancel": () => {
      S.editingSpeaker = null;
      renderRegion("overlay");
      tourRefresh();
    },
    "spk-save": () => {
      const s = cur();
      const name = S.speakerDraft.trim();
      if (!s || !S.editingSpeaker || !name) return;
      const key = S.editingSpeaker;
      s.speakers[key] = name;
      s.revision += 1;
      S.editingSpeaker = null;
      renderAll();
      toast("Speaker renamed");
      tourEvent("speakerRenamed", { key });
    },
    "seg-edit": (el) => {
      const s = cur();
      S.editingSeg = Number(el.dataset.i);
      S.segDraft = s.segs[S.editingSeg].text;
      renderRegion("overlay");
      root.querySelector('[data-input="seg"]')?.focus();
    },
    "seg-cancel": () => {
      S.editingSeg = null;
      renderRegion("overlay");
    },
    "seg-save": () => {
      const s = cur();
      if (!s || S.editingSeg === null || !S.segDraft.trim()) return;
      s.segs[S.editingSeg].text = S.segDraft.trim();
      s.revision += 1;
      S.editingSeg = null;
      renderAll();
      toast("Segment saved");
    },
    "player-toggle": () => {
      const s = cur();
      const p = s.player;
      if (p.playing) s.player = { playing: false, t: playerTime(s), since: 0 };
      else {
        s.player = { playing: true, t: p.t, since: Date.now() };
        if (!S.playerHinted) {
          S.playerHinted = true;
          toast("Im Demo läuft die Aufnahme ohne Ton.", "info");
        }
      }
      renderRegion("thread");
    },
    "player-seek": (el, event) => {
      const s = cur();
      const rect = el.getBoundingClientRect();
      const t = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * FILE.seconds;
      s.player = { playing: s.player.playing, t, since: Date.now() };
      renderRegion("thread");
    },
    quick: (el) => {
      const q = QUICK.find(([key]) => key === el.dataset.key);
      if (q) sendChat(q[2], { quick: q[0] });
    },
    ask: (el) => sendChat(el.dataset.q),
    send: () => sendChat(S.draft),
    mic: () => {
      if (S.command.state === "recording") stopCommand();
      else if (S.command.state === "idle") startCommand();
    },
    "review-dismiss": () => {
      S.review = false;
      S.draft = "";
      renderRegion("composer");
    },
    "confirm-action": (el) => {
      const s = cur();
      const msg = s.messages.find((m) => m.id === el.dataset.msg);
      if (!msg || !msg.action) return;
      msg.action.status = "confirmed";
      renderRegion("thread");
      tourRefresh();
      later(() => {
        msg.action.status = "executing";
        renderRegion("thread");
        later(() => {
          msg.action.status = "completed";
          renderRegion("thread");
          toast("Entwurf gespeichert");
          tourEvent("actionDone");
        }, 700);
      }, 400);
    },
    "cancel-action": (el) => {
      const s = cur();
      const msg = s.messages.find((m) => m.id === el.dataset.msg);
      if (!msg || !msg.action) return;
      msg.action.status = "cancelled";
      renderRegion("thread");
    },
    download: (el) => download(el.dataset.msg, el.dataset.ext),
    tts: (el) => playTts(el.dataset.msg),
    "voice-toggle": () => {
      toggleVoice();
      tourEvent("voiceToggled");
    },
    "open-settings": () => {
      S.draftSettings = { ...S.settings };
      S.confirmDelete = false;
      S.overlay = "settings";
      S.menu = null;
      renderRegion("overlay", { resetScroll: true });
      tourEvent("settingsOpened");
    },
    "setting-toggle": (el) => {
      const key = el.dataset.key;
      S.draftSettings[key] = !S.draftSettings[key];
      if (key === "tts" && !S.draftSettings.tts) {
        S.draftSettings.ttsAuto = false;
        S.draftSettings.ttsPlay = false;
      }
      renderRegion("overlay");
    },
    "save-settings": () => {
      const voiceChanged = S.draftSettings.voiceEngine !== S.settings.voiceEngine;
      S.settings = { ...S.draftSettings };
      S.overlay = null;
      if (voiceChanged && S.voice.on) stopVoice();
      renderAll();
      toast("Settings saved");
    },
    "delete-ask": () => {
      S.confirmDelete = true;
      renderRegion("overlay");
    },
    "delete-cancel": () => {
      S.confirmDelete = false;
      renderRegion("overlay");
    },
    "delete-all": () => {
      const count = S.sessions.length;
      stopVoice();
      S.sessions = [];
      S.currentId = null;
      S.overlay = null;
      renderAll();
      toast(count > 0 ? `Deleted ${count} session(s)` : "No sessions to delete");
    },
    "close-overlay": () => {
      S.overlay = null;
      S.editingSpeaker = null;
      S.editingSeg = null;
      renderRegion("overlay");
      tourRefresh();
    },
  };

  // After a click in the demo, bring the next highlighted element into view (once per target).
  let lastUserAct = 0;
  let scrolledFor = "";
  root.addEventListener("pointerdown", () => (lastUserAct = Date.now()));
  tourEl.addEventListener("pointerdown", () => (lastUserAct = Date.now()));

  root.addEventListener("click", (event) => {
    const el = event.target.closest("[data-act]");
    if (S.menu && !event.target.closest(".a-menu") && (!el || !["attach", "theme-menu"].includes(el.dataset.act))) {
      const region = S.menu === "theme" ? "sidebar" : "composer";
      S.menu = null;
      renderRegion(region);
      if (!el) return;
    }
    if (!el || el.disabled) return;
    const handler = ACTIONS[el.dataset.act];
    if (handler) handler(el, event);
  });

  root.addEventListener("input", (event) => {
    const el = event.target;
    switch (el.dataset.input) {
      case "draft": {
        S.draft = el.value;
        const send = root.querySelector('[data-act="send"]');
        const s = cur();
        if (send) send.disabled = !S.draft.trim() || chatBusy(s) || S.command.state !== "idle";
        growTextarea();
        break;
      }
      case "query":
        S.query = el.value;
        renderRegion("list");
        break;
      case "speaker": {
        S.speakerDraft = el.value;
        const save = root.querySelector('[data-act="spk-save"]');
        if (save) save.disabled = !el.value.trim();
        break;
      }
      case "seg":
        S.segDraft = el.value;
        break;
      default:
        break;
    }
  });

  root.addEventListener("change", (event) => {
    const el = event.target;
    if (el.dataset.setting && S.draftSettings) {
      S.draftSettings[el.dataset.setting] = el.value;
      renderRegion("overlay");
    }
  });

  root.addEventListener("keydown", (event) => {
    const el = event.target;
    if (event.key === "Enter" && !event.shiftKey && el.dataset.input === "draft") {
      event.preventDefault();
      sendChat(S.draft);
    } else if (event.key === "Enter" && el.dataset.input === "speaker") {
      event.preventDefault();
      ACTIONS["spk-save"]();
    } else if (event.key === "Escape") {
      if (S.menu) {
        S.menu = null;
        renderAll();
      } else if (S.overlay) {
        ACTIONS["close-overlay"]();
      }
    }
  });

  // ---------------------------------------------------------------- guided tour

  const STEPS = [
    {
      id: "new",
      title: "Neue Sitzung anlegen",
      body: "<p><b>Die App-Oberfläche ist anklickbar.</b> Klicken Sie direkt hinein, auf die gelb markierte Stelle mit „Hier klicken“. Oder lassen Sie es sich mit „Zeig es mir“ vorführen.</p><p>Alles hier ist nachgestellt: Meeting und Antworten sind erfunden, es läuft keine KI und nichts wird gespeichert.</p><p>In der App gehört eine Sitzung zu einer Aufnahme. Darin liegen später das Transkript und Ihr Chat dazu.</p>",
      hint: () => (S.collapsed ? "Klicken Sie ganz links auf das <b>+</b> (New session)." : "Klicken Sie links auf <b>New session</b>."),
      target: "new-session",
      auto: () => ACTIONS["new-session"](),
    },
    {
      id: "upload",
      title: "Aufnahme hinzufügen",
      body: "<p>Sie laden eine Audiodatei hoch (<code>.mp3</code> oder <code>.wav</code>) oder nehmen direkt mit dem Mikrofon auf.</p><p>In der Vorführung wird nichts hochgeladen. Stattdessen erscheint ein erfundenes Projektmeeting mit drei Personen.</p>",
      hint: () => (S.menu === "attach" ? "Wählen Sie <b>Upload meeting audio</b>." : "Klicken Sie unten im Eingabefeld auf das <b>+</b>."),
      target: () => (S.menu === "attach" ? "upload" : "attach"),
      auto: () => (S.menu === "attach" ? ACTIONS.upload() : ACTIONS.attach()),
    },
    {
      id: "transcribe",
      title: "Das KI-Team arbeitet",
      body: "<p>In der App schreibt jetzt Whisper mit, pyannote erkennt die Stimmen, dann fügt Transcibio beides zusammen. Alles passiert auf Ihrem Rechner, nichts geht ins Internet.</p><p style=\"color:var(--muted)\">Hier ist der Fortschritt nur nachgestellt und stark verkürzt. In der App hängt die Dauer von der Länge der Aufnahme und Ihrer Grafikkarte ab.</p>",
      hint: () => (cur() && cur().phase === "recording" ? "Klicken Sie auf den roten <b>Stopp</b>-Knopf, um die Aufnahme zu beenden." : "Einen Moment, das Transkript entsteht …"),
      wait: () => !(cur() && cur().phase === "recording"),
      target: () => (cur() && cur().phase === "recording" ? "stop-recording" : null),
      auto: () => (cur() && cur().phase === "recording" ? ACTIONS["stop-recording"]() : null),
    },
    {
      id: "transcript",
      title: "Transkript lesen",
      body: "<p>Fertig! Transcibio hat der Sitzung auch gleich einen passenden Titel gegeben.</p><p>Das Transkript zeigt, wer wann was gesagt hat. Mit dem Play-Knopf hören Sie die Aufnahme nach.</p>",
      hint: "Klicken Sie auf <b>Transcript</b>, um es aufzuklappen.",
      target: "transcript-toggle",
      auto: () => ACTIONS["toggle-transcript"](),
    },
    {
      id: "rename",
      title: "Sprecher benennen",
      body: "<p>pyannote unterscheidet die Stimmen, kennt aber keine Namen. Deshalb heißen die Sprecher zuerst SPEAKER_00, SPEAKER_01 und so weiter.</p><p>Den richtigen Namen tragen Sie einmal ein, dann steht er überall.</p>",
      hint: () => {
        if (S.overlay !== "transcript") return "Klicken Sie auf <b>Edit transcript</b>.";
        if (S.sheetTab !== "speakers") return "Wechseln Sie oben zum Reiter <b>Speakers</b>.";
        if (!S.editingSpeaker) return "Klicken Sie bei <b>SPEAKER_00</b> auf den Stift.";
        return "Wir haben „Frau Keller“ schon eingetragen. Klicken Sie auf das <b>Speichern</b>-Symbol.";
      },
      target: () => {
        if (S.overlay !== "transcript") return "edit-transcript";
        if (S.sheetTab !== "speakers") return "tab-speakers";
        if (!S.editingSpeaker) return "edit-spk-SPEAKER_00";
        return "save-spk";
      },
      auto: () => {
        if (S.overlay !== "transcript") ACTIONS["open-transcript-sheet"]();
        else if (S.sheetTab !== "speakers") ACTIONS["sheet-tab"]({ dataset: { tab: "speakers" } });
        else if (!S.editingSpeaker) ACTIONS["spk-edit"]({ dataset: { key: "SPEAKER_00" } });
        else ACTIONS["spk-save"]();
      },
    },
    {
      id: "ask",
      title: "Eine Frage stellen",
      body: "<p>Fragen Sie in Ihren eigenen Worten, so wie Sie eine Kollegin fragen würden.</p><p>Wir haben eine Frage vorbereitet. In der Vorführung sind die Antworten vorbereitet; in der App beantwortet das Sprachmodell jede Frage zu Ihrer Aufnahme.</p>",
      enter: () => {
        if (!S.draft.trim()) S.draft = "Bis wann soll der Designentwurf fertig sein?";
        renderRegion("composer");
      },
      hint: () => (chatBusy(cur()) ? "Die Antwort entsteht …" : "Klicken Sie unten rechts auf den <b>Pfeil</b> zum Senden."),
      wait: () => chatBusy(cur()),
      target: () => (chatBusy(cur()) ? null : "send"),
      auto: () => ACTIONS.send(),
    },
    {
      id: "quick",
      title: "Antworten mit Quellen",
      body: "<p>Unter jeder Antwort steht, aus welcher Stelle der Aufnahme sie stammt, mit Zeitangabe. So können Sie alles nachprüfen.</p><p>Für häufige Aufgaben gibt es Schnellbuttons im Transkript-Kasten.</p>",
      enter: () => later(() => highlight({ scroll: true }), 2600),
      hint: () => (chatBusy(cur()) ? "Die Zusammenfassung entsteht …" : "Klicken Sie oben im Transkript-Kasten auf <b>Zusammenfassen</b>."),
      wait: () => chatBusy(cur()),
      target: () => (chatBusy(cur()) ? null : "qa-summarize"),
      auto: () => ACTIONS.quick({ dataset: { key: "summarize" } }),
    },
    {
      id: "draft",
      title: "Entwürfe erstellen",
      body: "<p>Transcibio kann auch mitarbeiten: Es schlägt E-Mails und Aufgabenlisten vor. Sie prüfen den Entwurf und speichern ihn mit einem Klick als Datei.</p>",
      enter: () => {
        S.draft = "Schreib eine E-Mail an die Kundin mit dem Zeitplan.";
        renderRegion("composer");
      },
      hint: () => {
        if (chatBusy(cur())) return "Der Entwurf entsteht …";
        return pendingAction() ? "Prüfen Sie den Entwurf und klicken Sie auf <b>Confirm</b>." : "Senden Sie die vorbereitete Bitte mit dem <b>Pfeil</b>.";
      },
      wait: () => chatBusy(cur()) || actionRunning(),
      target: () => (chatBusy(cur()) ? null : pendingAction() ? "confirm-action" : "send"),
      auto: () => {
        const m = pendingAction();
        if (m) ACTIONS["confirm-action"]({ dataset: { msg: m.id } });
        else ACTIONS.send();
      },
    },
    {
      id: "voice",
      title: "Sprechen statt tippen",
      body: "<p>Im Sprachmodus fragen Sie laut und hören die Antwort, ganz ohne Tastatur. Wer dazwischen spricht, unterbricht die Antwort.</p><p>In der Vorführung bleibt das Mikrofon aus: Wir spielen eine erfundene Frage ab. Ist der Ton an, liest Ihr Browser die Antwort vor; in der App spricht Piper.</p>",
      hint: () => (S.voice.on ? "Hören Sie zu …" : "Klicken Sie unten auf <b>Sprachmodus</b>."),
      wait: () => S.voice.on,
      target: () => (S.voice.on ? null : "voice-toggle"),
      auto: () => (S.voice.on ? null : ACTIONS["voice-toggle"]()),
    },
    {
      id: "settings",
      title: "Einstellungen",
      enter: () => {
        if (S.voice.on) later(() => {
          stopVoice();
          renderRegion("voice");
          renderRegion("composer");
        }, 1500);
      },
      body: "<p>Unter <b>Settings</b> wählen Sie die Genauigkeit der Transkription, das Chat-Modell, den Denkmodus und die Stimme (Deutsch oder Englisch).</p><p>Jede Einstellung ist erklärt: Fahren Sie mit der Maus über die kleinen Fragezeichen.</p>",
      hint: () => (S.collapsed ? "Klicken Sie links unten auf das <b>Zahnrad</b>." : "Klicken Sie links unten auf <b>Settings</b>."),
      target: "settings",
      auto: () => ACTIONS["open-settings"](),
    },
    {
      id: "done",
      title: "Geschafft!",
      body: "<p>Sie kennen jetzt das Wichtigste. Zur Erinnerung: Das war eine Vorführung mit erfundenen Daten. Die echte App arbeitet auf Ihrem Rechner mit Ihren eigenen Aufnahmen.</p><p>Klicken Sie ruhig weiter:</p><ul style=\"margin:0 0 8px;padding-left:20px\"><li>weitere Fragen zum erfundenen Meeting stellen</li><li>die anderen Sprecher benennen (Herr Aydin, Frau Brandt)</li><li>in den Settings „TTS enabled“ einschalten und Antworten vorlesen lassen</li><li>links unten das dunkle Design wählen</li></ul>",
    },
  ];

  const tour = { active: true, idx: 0 };
  const currentStep = () => STEPS[tour.idx];
  const pendingAction = () => {
    const s = cur();
    return s && s.messages.find((m) => m.action && m.action.status === "proposed");
  };
  const actionRunning = () => {
    const s = cur();
    return !!(s && s.messages.find((m) => m.action && ["confirmed", "executing"].includes(m.action.status)));
  };

  function advance(toId) {
    const target = toId ? STEPS.findIndex((st) => st.id === toId) : tour.idx + 1;
    tour.idx = Math.min(target, STEPS.length - 1);
    const step = currentStep();
    if (step.enter) step.enter();
    renderTour();
    highlight();
  }

  function tourEvent(name, data = {}) {
    if (!tour.active) return;
    const id = currentStep().id;
    const done =
      (id === "new" && name === "sessionCreated") ||
      (id === "upload" && name === "uploaded") ||
      (id === "transcribe" && name === "transcribed") ||
      (id === "transcript" && name === "transcriptOpened") ||
      (id === "rename" && name === "speakerRenamed" && data.key === "SPEAKER_00") ||
      (id === "ask" && name === "answered") ||
      (id === "quick" && name === "answered" && data.quick === "summarize") ||
      (id === "draft" && name === "actionDone") ||
      (id === "voice" && name === "voiceAnswered") ||
      (id === "settings" && name === "settingsOpened");
    if (id === "upload" && name === "uploaded") {
      advance();
      return;
    }
    if (done && id === "rename") {
      renderTour();
      later(() => {
        if (S.overlay === "transcript") {
          S.overlay = null;
          renderRegion("overlay");
        }
        advance();
      }, 1000);
      return;
    }
    if (done && id === "new") {
      // A fresh session: the upload step starts from a clean composer.
      advance();
      return;
    }
    if (done) {
      later(() => advance(), id === "ask" ? 900 : 400);
    } else {
      tourRefresh();
    }
  }

  function tourRefresh() {
    renderTour();
    highlight();
  }

  // "Hier klicken" label next to the highlighted element; hidden when the element is scrolled
  // out of view. Re-placed on every tick, so it follows scrolling and opening panels.
  function placePointer() {
    const ptr = root.querySelector("[data-tour-pointer]");
    if (!ptr) return;
    const el = root.querySelector(".tour-target");
    const frame = root.querySelector("[data-a-root]");
    if (!el || !frame) {
      ptr.hidden = true;
      return;
    }
    // Covered by an open dialog or panel: the element can't be clicked, so no label.
    const overlay = root.querySelector('[data-region="overlay"]');
    if (overlay && overlay.childElementCount && !overlay.contains(el)) {
      ptr.hidden = true;
      return;
    }
    const fr = frame.getBoundingClientRect();
    const er = el.getBoundingClientRect();
    const clip = el.closest(".a-thread, .a-sheet, .a-dialog, .a-list");
    const cr = clip ? clip.getBoundingClientRect() : fr;
    if (er.width === 0 || er.bottom < cr.top + 4 || er.top > cr.bottom - 4) {
      ptr.hidden = true;
      return;
    }
    ptr.hidden = false;
    const pw = ptr.offsetWidth;
    const ph = ptr.offsetHeight;
    let top = er.top - fr.top - ph - 12;
    let below = false;
    if (top < 6) {
      top = er.bottom - fr.top + 12;
      below = true;
    }
    const center = er.left - fr.left + er.width / 2;
    const left = Math.max(6, Math.min(center - pw / 2, fr.width - pw - 6));
    ptr.style.top = `${top}px`;
    ptr.style.left = `${left}px`;
    ptr.style.setProperty("--arrow-x", `${Math.max(14, Math.min(center - left, pw - 14))}px`);
    ptr.classList.toggle("is-below", below);
  }

  function highlight(opts = {}) {
    root.querySelectorAll(".tour-target").forEach((el) => el.classList.remove("tour-target"));
    const done = () => placePointer();
    if (!tour.active) return done();
    const step = currentStep();
    const name = typeof step.target === "function" ? step.target() : step.target;
    if (!name) return done();
    const el = [...root.querySelectorAll(`[data-tour="${name}"]`)].find((e) => e.offsetParent !== null && !e.disabled);
    if (!el) return done();
    const overlay = root.querySelector('[data-region="overlay"]');
    if (overlay && overlay.childElementCount && !overlay.contains(el)) return done();
    el.classList.add("tour-target");
    placePointer();
    const key = `${tour.idx}:${name}`;
    if (Date.now() - lastUserAct < 4000 && scrolledFor !== key && !el.closest(".a-thread")) {
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight;
      if (r.bottom > vh - 16 || r.top < 84) {
        scrolledFor = key;
        const delta = r.bottom > vh - 16 ? r.bottom - vh + 56 : r.top - 120;
        window.scrollBy({ top: delta, behavior: "smooth" });
      }
    }
    if (opts.scroll) {
      const thread = el.closest(".a-thread");
      if (thread) {
        const tr = thread.getBoundingClientRect();
        const er = el.getBoundingClientRect();
        if (er.top < tr.top + 8 || er.bottom > tr.bottom - 8) {
          thread.scrollTo({ top: thread.scrollTop + er.top - tr.top - tr.height / 3, behavior: "smooth" });
        }
      }
    }
  }

  function renderTour() {
    const step = currentStep();
    const total = STEPS.length - 1;
    const isDone = step.id === "done";
    const hint = typeof step.hint === "function" ? step.hint() : step.hint;
    const waiting = typeof step.wait === "function" ? step.wait() : !!step.wait;
    const canAuto = step.auto && !waiting;
    const icon = window.TB.icon;
    tourEl.innerHTML = `
      <div class="tour-progress" aria-hidden="true">${STEPS.slice(0, total)
        .map((_, i) => `<span class="${i < tour.idx ? "done" : i === tour.idx ? "now" : ""}"></span>`)
        .join("")}</div>
      <div class="tour-tag">${icon("info")}Vorführung · erfundene Daten</div>
      <div class="tour-count">${isDone ? "Tour abgeschlossen" : `Schritt ${tour.idx + 1} von ${total}`}</div>
      <h3>${step.title}</h3>
      <div class="tour-text">${step.body}</div>
      ${hint ? `<div class="tour-hint${waiting ? " is-wait" : ""}">${icon(waiting ? "loader" : "pointer")}<div>${hint}</div></div>` : ""}
      <div class="tour-actions">
        ${canAuto ? `<button class="btn btn-secondary btn-small" data-tour-act="auto">${icon("forward")}Zeig es mir</button>` : ""}
        ${isDone ? `<a class="btn btn-primary btn-small" href="#installieren">${icon("download")}Jetzt installieren</a><button class="btn btn-secondary btn-small" data-tour-act="restart">${icon("rotate")}Tour neu starten</button>` : ""}
      </div>
      <div class="tour-foot">
        <button class="link-btn" data-tour-act="restart">${icon("rotate")}Neu starten</button>
        ${synth ? `<button class="link-btn" data-tour-act="sound" aria-pressed="${S.sound}">${icon(S.sound ? "volume" : "volumeOff")}Ton ${S.sound ? "an" : "aus"}</button>` : ""}
        ${isDone ? "" : `<button class="link-btn" data-tour-act="skip">${icon("forward")}Ohne Tour erkunden</button>`}
      </div>`;
  }

  tourEl.addEventListener("click", (event) => {
    const el = event.target.closest("[data-tour-act]");
    if (!el) return;
    const act = el.dataset.tourAct;
    if (act === "auto") {
      const step = currentStep();
      if (step.auto) step.auto();
    } else if (act === "restart") {
      reset();
    } else if (act === "sound") {
      S.sound = !S.sound;
      if (!S.sound) hush();
      renderTour();
    } else if (act === "skip") {
      skipTour();
    }
  });

  function skipTour() {
    let s = cur();
    if (!s) s = newSession();
    if (s.phase !== "ready") {
      jobs.delete(`tx-${s.id}`);
      s.phase = "ready";
      s.title = AUTO_TITLE;
    }
    S.menu = null;
    S.overlay = null;
    tour.idx = STEPS.length - 1;
    renderAll({ toBottom: true });
  }

  function reset() {
    clearBucket(timers);
    stopVoice();
    jobs.clear();
    seen.clear();
    S = freshState();
    tour.active = true;
    tour.idx = 0;
    renderAll();
  }

  S = freshState();
  mount();
  renderAll();
  window.setInterval(() => {
    tick();
    placePointer();
  }, 200);
  window.addEventListener("resize", () => {
    if (narrow() && !S.collapsed) {
      S.collapsed = true;
      renderRegion("sidebar");
    }
  });
})();
