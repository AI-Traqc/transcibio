// Starts the backend (uvicorn, :8000) and frontend (Vite, :5173) in one terminal on Windows,
// macOS and Linux. Usage: `node start.mjs` from the repo root; Ctrl+C stops both. If one
// server exits on its own (e.g. port already in use), the other is stopped too.
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const isWindows = process.platform === "win32";
const python = join(root, ".venv", ...(isWindows ? ["Scripts", "python.exe"] : ["bin", "python"]));
const vite = join(root, "frontend", "node_modules", "vite", "bin", "vite.js");
const tty = Boolean(process.stdout.isTTY);
const paint = (code, text) => (tty ? `\x1b[${code}m${text}\x1b[0m` : text);

if (!existsSync(python) || !existsSync(vite)) {
  console.error(paint(31, "Setup incomplete:"));
  if (!existsSync(python)) console.error(`  no Python venv at ${python}`);
  if (!existsSync(vite)) console.error("  frontend deps missing (run `npm install` in frontend/)");
  console.error("See docs/development.md → Install.");
  process.exit(1);
}

const ollamaUrl = process.env.TRANSCIBIO_OLLAMA_TAGS_URL ?? "http://127.0.0.1:11434/api/tags";
try {
  await fetch(ollamaUrl, { signal: AbortSignal.timeout(1500) });
} catch {
  console.warn(
    paint(33, `Ollama is not reachable at ${ollamaUrl} — chat will use fallback replies.`) +
      "\n  Start it with `ollama serve` (ignore this if you use LM Studio).",
  );
}

const services = [
  {
    name: "api",
    color: 36,
    cwd: root,
    command: python,
    args: ["-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"]
      .concat(tty ? ["--use-colors"] : []),
  },
  {
    // Vite is run through node directly rather than `npm run dev`: on Windows npm is a .cmd
    // batch file, which needs a shell and prompts "Terminate batch job (Y/N)?" on Ctrl+C.
    name: "web",
    color: 35,
    cwd: join(root, "frontend"),
    command: process.execPath,
    args: [vite, "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
  },
];
// Output is piped (for the prefixes): keep colors only when we're on a terminal, and make
// Python output unbuffered UTF-8 so lines show up immediately and umlauts don't crash prints.
const env = { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" };
env[tty ? "FORCE_COLOR" : "NO_COLOR"] = "1";

console.log(paint(1, "Starting Transcibio → http://127.0.0.1:5173  (Ctrl+C to stop)"));

let stopping = false;
let exitCode = 0;
let running = services.length;

const children = services.map(({ name, color, cwd, command, args }) => {
  const child = spawn(command, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  const prefix = paint(color, `[${name}]`);
  for (const stream of [child.stdout, child.stderr]) {
    createInterface({ input: stream }).on("line", (line) => console.log(`${prefix} ${line}`));
  }
  child.on("error", (error) => console.error(`${prefix} failed to start: ${error.message}`));
  child.on("close", (code) => {
    running -= 1;
    if (!stopping) {
      console.error(paint(31, `${prefix} exited with code ${code ?? 1} — stopping everything.`));
      exitCode = code || 1;
      stop();
    }
    if (running === 0) process.exit(exitCode);
  });
  return child;
});

function stop() {
  stopping = true;
  for (const child of children) {
    if (child.exitCode !== null || child.signalCode !== null) continue;
    // taskkill /T also ends grandchildren (uvicorn's reload worker would otherwise keep :8000).
    if (isWindows) spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    else child.kill("SIGTERM");
  }
}

// On Windows, Ctrl+C already reaches every process in the console, so let the servers shut down
// gracefully and only force-kill on a second Ctrl+C. Elsewhere, forward SIGTERM to the children.
process.on("SIGINT", () => {
  if (isWindows && !stopping) stopping = true;
  else stop();
});
process.on("SIGTERM", stop);
