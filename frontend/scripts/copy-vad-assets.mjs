// Copies the Silero VAD model + ONNX Runtime wasm into public/vad/ so browser
// voice mode works fully offline (no CDN fetch). Runs on postinstall; the copied
// assets are gitignored and regenerated from node_modules.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dest = join(root, "public", "vad");
mkdirSync(dest, { recursive: true });

const assets = [
  "@ricky0123/vad-web/dist/silero_vad_v5.onnx",
  "@ricky0123/vad-web/dist/silero_vad_legacy.onnx",
  "@ricky0123/vad-web/dist/vad.worklet.bundle.min.js",
  // ONNX Runtime loads the wasm through a .mjs glue loader (ort 1.19+), so both
  // the .mjs and the .wasm must be present for each backend variant.
  "onnxruntime-web/dist/ort-wasm-simd-threaded.mjs",
  "onnxruntime-web/dist/ort-wasm-simd-threaded.wasm",
  "onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.mjs",
  "onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.wasm",
];

let copied = 0;
for (const rel of assets) {
  const src = join(root, "node_modules", rel);
  if (existsSync(src)) {
    copyFileSync(src, join(dest, rel.split("/").pop()));
    copied += 1;
  } else {
    console.warn(`[copy-vad-assets] missing: ${rel}`);
  }
}
console.log(`[copy-vad-assets] copied ${copied}/${assets.length} assets to public/vad/`);
