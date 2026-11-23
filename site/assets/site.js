/* Shared helpers for the Transcibio website: icons (Lucide, ISC licence), header menu,
   video chapters, the "how it works" explorer, copy buttons and the help search. */
(() => {
  "use strict";

  const ICONS = {
    plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    panelLeft: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
    settings:
      '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/>',
    square: '<rect width="18" height="18" x="3" y="3" rx="2"/>',
    arrowUp: '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
    volume: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
    volumeOff: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="22" x2="16" y1="9" y2="15"/><line x1="16" x2="22" y1="9" y2="15"/>',
    chevronDown: '<path d="m6 9 6 6 6-6"/>',
    chevronRight: '<path d="m9 18 6-6-6-6"/>',
    pencil: '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/>',
    quote:
      '<path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z"/><path d="M15 21c3 0 7-1 7-8V5c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2h.75c0 2.25.25 4-2.75 4v3c0 1 0 1 1 1z"/>',
    fileText:
      '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    checkCircle: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    download:
      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
    loader: '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
    sparkles:
      '<path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>',
    upload:
      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/>',
    message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M13 8H7"/><path d="M17 12H7"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    more: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    fileAudio:
      '<path d="M17.5 22h.5a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v3"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M2 19a2 2 0 1 1 4 0v1a2 2 0 1 1-4 0v-4a6 6 0 0 1 12 0v4a2 2 0 1 1-4 0v-1a2 2 0 1 1 4 0"/>',
    disc: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="2"/>',
    play: '<polygon points="6 3 20 12 6 21 6 3"/>',
    pause: '<rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/>',
    save: '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
    copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    lock: '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    ear: '<path d="M6 8.5a6.5 6.5 0 1 1 13 0c0 6-6 6-6 10a3.5 3.5 0 1 1-7 0"/><path d="M15 8.5a2.5 2.5 0 0 0-5 0v1a2 2 0 1 1 0 4"/>',
    fingerprint:
      '<path d="M12 10a2 2 0 0 0-2 2c0 1.02-.1 2.51-.26 4"/><path d="M14 13.12c0 2.38 0 6.38-1 8.88"/><path d="M17.29 21.02c.12-.6.43-2.3.5-3.02"/><path d="M2 12a10 10 0 0 1 18-6"/><path d="M2 16h.01"/><path d="M21.8 16c.2-2 .131-5.354 0-6"/><path d="M5 19.5C5.5 18 6 15 6 12a6 6 0 0 1 .34-2"/><path d="M8.65 22c.21-.66.45-1.32.57-2"/><path d="M9 6.8a6 6 0 0 1 9 5.2v2"/>',
    book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    terminal: '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>',
    monitor: '<rect width="20" height="14" x="2" y="3" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/>',
    rotate: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    forward: '<polygon points="13 19 22 12 13 5 13 19"/><polygon points="2 19 11 12 2 5 2 19"/>',
    pointer: '<path d="m9 9 5 12 1.8-5.2L21 14Z"/><path d="M7.2 2.2 8 5.1"/><path d="m5.1 8-2.9-.8"/><path d="M14 4.1 12 6"/><path d="m6 12-1.9 2"/>',
    external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    cloud: '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
    gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13"/><path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/><path d="M7.5 8a2.5 2.5 0 0 1 0-5A4.8 8 0 0 1 12 8a4.8 8 0 0 1 4.5-5 2.5 2.5 0 0 1 0 5"/>',
    menu: '<line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/>',
    windows: '<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="8" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/><rect x="13" y="13" width="8" height="8" rx="1"/>',
    apple: '<path d="M12 20.94c1.5 0 2.75 1.06 4 1.06 3 0 6-8 6-12.22A4.91 4.91 0 0 0 17 5c-2.22 0-4 1.44-5 2-1-.56-2.78-2-5-2a4.9 4.9 0 0 0-5 4.78C2 14 5 22 8 22c1.25 0 2.5-1.06 4-1.06Z"/><path d="M10 2c1 .5 2 2 2 5"/>',
    linux: '<path d="M12 2c-2.2 0-3.5 1.9-3.5 4.4 0 1.6.4 2.6-.6 4.3C6.7 12.8 5 15 5 17.2 5 19.9 7.8 22 12 22s7-2.1 7-4.8c0-2.2-1.7-4.4-2.9-6.5-1-1.7-.6-2.7-.6-4.3C15.5 3.9 14.2 2 12 2Z"/><path d="M10 8h.01"/><path d="M14 8h.01"/><path d="M10.5 11c.9.6 2.1.6 3 0"/>',
    cpu: '<rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
    github:
      '<path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/><path d="M9 18c-4.51 2-5-2-7-2"/>',
  };

  function icon(name, cls = "icon") {
    return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      let ok = false;
      try {
        ok = document.execCommand("copy");
      } catch {
        ok = false;
      }
      area.remove();
      return ok;
    }
  }

  window.TB = { icon, escapeHtml, copyText };

  // Static [data-icon] placeholders in the HTML.
  function hydrateIcons(scope = document) {
    scope.querySelectorAll("[data-icon]").forEach((el) => {
      el.outerHTML = icon(el.dataset.icon, el.className ? `icon ${el.className}` : "icon");
    });
  }
  window.TB.hydrateIcons = hydrateIcons;
  hydrateIcons();

  // Copy buttons on any .code block (also those rendered later by install.js).
  document.addEventListener("click", async (event) => {
    const button = event.target.closest(".copy-btn");
    if (!button) return;
    const block = button.closest(".code");
    const text = block?.dataset.copy ?? "";
    const ok = await copyText(text);
    const label = button.querySelector("span");
    if (label) {
      label.textContent = ok ? "Kopiert" : "Bitte markieren";
      window.setTimeout(() => (label.textContent = "Kopieren"), 1600);
    }
  });

  // Header menu (mobile).
  const menuButton = document.querySelector(".menu-toggle");
  const nav = document.querySelector(".site-nav");
  if (menuButton && nav) {
    menuButton.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      menuButton.setAttribute("aria-expanded", String(open));
    });
    nav.addEventListener("click", (event) => {
      if (event.target.closest("a")) {
        nav.classList.remove("is-open");
        menuButton.setAttribute("aria-expanded", "false");
      }
    });
  }

  // Video chapters: jump on click, highlight the current one while playing.
  const video = document.getElementById("explainer");
  const chapterButtons = [...document.querySelectorAll("[data-seek]")];
  if (video && chapterButtons.length) {
    const times = chapterButtons.map((b) => Number(b.dataset.seek));
    chapterButtons.forEach((button) => {
      button.addEventListener("click", () => {
        video.currentTime = Number(button.dataset.seek);
        video.play().catch(() => {});
      });
    });
    video.addEventListener("timeupdate", () => {
      let current = 0;
      times.forEach((t, i) => {
        if (video.currentTime >= t - 0.25) current = i;
      });
      chapterButtons.forEach((b, i) => b.classList.toggle("is-current", i === current));
    });
  }

  // "How it works": one model per stage; the detail panel shows the selected one.
  const STAGES = {
    whisper: {
      title: "Whisper schreibt mit",
      text: "Whisper hört die Aufnahme an und macht daraus Text, mit Zeitangaben zu jedem Satz. Vorher schneidet es Stille heraus und teilt die Aufnahme in Stücke von höchstens 30 Sekunden.",
      extra: "In den Einstellungen wählen Sie, wie gründlich: Fast, Balanced oder Quality. Gründlicher heißt genauer, aber langsamer.",
      facts: [
        ["Modell", "faster-whisper small / medium / large-v3"],
        ["Größe", "0,5 / 1,5 / 3 GB"],
        ["Nötig?", "Ja (Standard: medium)"],
      ],
    },
    pyannote: {
      title: "pyannote erkennt, wer spricht",
      text: "pyannote hört nicht auf die Worte, sondern auf die Stimmen. Es merkt, wann eine andere Person spricht, und vergibt Kennungen wie SPEAKER_00 und SPEAKER_01.",
      extra: "Namen kennt pyannote nicht. Die tragen Sie mit einem Klick selbst ein, danach stehen sie überall im Transkript.",
      facts: [
        ["Modell", "speaker-diarization-community-1"],
        ["Größe", "unter 100 MB"],
        ["Nötig?", "Optional (kostenloser Hugging-Face-Token)"],
      ],
    },
    merge: {
      title: "Zusammenführen zum Transkript",
      text: "Transcibio legt beides übereinander: was gesagt wurde (Whisper) und wer gesprochen hat (pyannote). Heraus kommt ein Transkript mit Zeit, Sprecher und Text.",
      extra: "Fehler korrigieren Sie direkt in der App. Auf Wunsch schlägt das Sprachmodell Korrekturen vor.",
      facts: [
        ["Ergebnis", "Zeit · Sprecher · Text"],
        ["Bearbeiten", "Wörter und Namen"],
        ["Gespeichert in", "Ordner data/ auf Ihrem Rechner"],
      ],
    },
    llm: {
      title: "Das Sprachmodell antwortet",
      text: "Wenn Sie eine Frage stellen, sucht Transcibio die passenden Stellen im Transkript heraus. Das Sprachmodell formuliert daraus die Antwort und nennt die Quellen, mit Zeitangabe.",
      extra: "Es schreibt auch Zusammenfassungen, Kernpunkte, Übersetzungen und Entwürfe für E-Mails und Aufgabenlisten. Das Modell läuft über Ollama auf Ihrem Rechner.",
      facts: [
        ["Modell", "gemma4:e4b (größer: gemma4:26b)"],
        ["Größe", "7 / 18 GB"],
        ["Nötig?", "Ja (sonst nur einfache feste Antworten)"],
      ],
    },
    voice: {
      title: "Piper und Kokoro sprechen",
      text: "Auf Wunsch liest Transcibio jede Antwort vor: Piper auf Deutsch, Kokoro auf Englisch. Im Sprachmodus führen Sie so ein Gespräch ganz ohne Tastatur.",
      extra: "Wer dazwischen spricht, unterbricht die Antwort, wie in einem echten Gespräch. Mit Kopfhörern hört sich die App nicht selbst.",
      facts: [
        ["Stimmen", "Piper thorsten-high · Kokoro v1.0"],
        ["Größe", "in der App enthalten"],
        ["Nötig?", "Optional"],
      ],
    },
  };
  const nodes = [...document.querySelectorAll(".pipe-node")];
  const detail = document.getElementById("pipe-detail");
  function showStage(key) {
    const stage = STAGES[key];
    if (!stage || !detail) return;
    nodes.forEach((n) => n.setAttribute("aria-selected", String(n.dataset.stage === key)));
    detail.innerHTML = `
      <div>
        <h3>${stage.title}</h3>
        <p>${stage.text}</p>
        <p style="color:var(--muted)">${stage.extra}</p>
      </div>
      <dl class="pipe-facts">${stage.facts
        .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`)
        .join("")}</dl>`;
  }
  nodes.forEach((node) => {
    node.addEventListener("click", () => showStage(node.dataset.stage));
    node.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      const i = nodes.indexOf(node);
      const next = nodes[(i + (event.key === "ArrowRight" ? 1 : nodes.length - 1)) % nodes.length];
      next.focus();
      showStage(next.dataset.stage);
    });
  });
  if (nodes.length) showStage("whisper");

  // Help: filter troubleshooting entries by system and search text.
  const help = document.getElementById("trouble");
  if (help) {
    const search = document.getElementById("trouble-search");
    const chips = [...document.querySelectorAll("[data-os-filter]")];
    const items = [...help.querySelectorAll("details")];
    const empty = document.getElementById("trouble-empty");
    let os = "all";
    const apply = () => {
      const q = (search?.value || "").trim().toLowerCase();
      let shown = 0;
      items.forEach((item) => {
        const itemOs = (item.dataset.os || "all").split(" ");
        const osOk = os === "all" || itemOs.includes("all") || itemOs.includes(os);
        const textOk = !q || item.textContent.toLowerCase().includes(q);
        item.hidden = !(osOk && textOk);
        if (!item.hidden) shown += 1;
      });
      if (empty) empty.hidden = shown > 0;
    };
    chips.forEach((chip) =>
      chip.addEventListener("click", () => {
        os = chip.dataset.osFilter;
        chips.forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
        apply();
      }),
    );
    search?.addEventListener("input", apply);
    window.TB.setHelpOs = (value) => {
      const chip = chips.find((c) => c.dataset.osFilter === value);
      chip?.click();
    };
  }
})();
