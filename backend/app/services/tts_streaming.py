"""Streaming TTS engines for voice mode.

Each engine turns a chunk of text into raw 16-bit little-endian mono PCM. The
voice-turn layer is responsible for splitting an answer into sentence chunks and
for framing/streaming the PCM to the browser; engines only synthesize.

Two engines are supported:
- ``piper``  — German primary (subprocess, ``de_DE-thorsten-high``, 22.05 kHz)
- ``kokoro`` — English example (in-process ONNX, 24 kHz)

Both expose the same :class:`StreamingTtsEngine` protocol so they are
interchangeable behind the WebSocket. Engine construction is comparatively
expensive (Kokoro loads a ~310 MB model), so build them once and reuse via
:class:`VoiceEngineRegistry`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Protocol, runtime_checkable

# Hard ceiling on how long we wait for Piper to synthesize one sentence before
# treating the process as wedged and killing it. Sentences synthesize in well under
# a second; this only guards against a stuck process never emitting its output path.
_PIPER_SYNTH_TIMEOUT_SECONDS = 30.0

_PIPER_DEFAULT_SAMPLE_RATE = 22050
_PIPER_DEFAULT_LANGUAGE = "de"
_KOKORO_SAMPLE_RATE = 24000


class StreamingTtsError(RuntimeError):
    """Synthesis failed for a reason that may be transient (engine ran, errored)."""


class StreamingTtsUnavailable(StreamingTtsError):
    """The engine could not be constructed (missing binary, model, or dependency)."""


@runtime_checkable
class StreamingTtsEngine(Protocol):
    name: str
    voice: str
    sample_rate: int
    language: str  # ISO-639-1 (e.g. "de", "en"); the language this engine can speak

    def synthesize_pcm(self, text: str) -> bytes:
        """Return raw int16 little-endian mono PCM for ``text`` (empty for blank)."""
        ...


def _read_piper_config(model_path: str) -> dict:
    config_path = Path(f"{model_path}.json")
    try:
        # Piper config JSON is UTF-8; the Windows default (cp1252) mis-decodes it.
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _piper_sample_rate(config: dict) -> int:
    rate = config.get("audio", {}).get("sample_rate")
    return int(rate) if isinstance(rate, int) else _PIPER_DEFAULT_SAMPLE_RATE


def _piper_language(config: dict) -> str:
    # Piper voice config carries {"language": {"code": "de_DE", "family": "de", ...}}.
    lang = config.get("language")
    if isinstance(lang, dict):
        family = lang.get("family") or lang.get("code")
        if isinstance(family, str) and family.strip():
            return family.strip()[:2].lower()
    return _PIPER_DEFAULT_LANGUAGE


def _read_wav_pcm(path: str) -> bytes:
    """Return the raw int16 LE mono PCM data chunk of a Piper-written WAV file."""
    with wave.open(path, "rb") as wav:
        return wav.readframes(wav.getnframes())


class PiperStreamingEngine:
    """German TTS via a long-lived Piper process; the voice model is loaded once.

    The previous implementation spawned a fresh ``piper.exe`` per sentence, reloading
    the ONNX voice model + onnxruntime each time — the dominant German-TTS cost on the
    streaming voice path. Instead we keep one process alive: it reads one line of text
    per utterance on stdin and (via ``--output_dir``) writes one WAV per line, printing
    that WAV's path to stdout. We read the path, parse the WAV to raw PCM, and delete
    the file. A lock serialises the stdin/stdout exchange because the engine is shared
    across turns and threads via :class:`VoiceEngineRegistry`.
    """

    name = "piper"

    def __init__(self, *, piper_bin: str, model_path: str, voice: str | None = None) -> None:
        if not piper_bin or not Path(piper_bin).exists():
            raise StreamingTtsUnavailable(f"Piper binary not found: {piper_bin or '<unset>'}")
        if not model_path or not Path(model_path).exists():
            raise StreamingTtsUnavailable(f"Piper model not found: {model_path or '<unset>'}")
        self._bin = piper_bin
        self._model = model_path
        config = _read_piper_config(model_path)
        self.voice = voice or Path(model_path).stem
        self.sample_rate = _piper_sample_rate(config)
        self.language = _piper_language(config)
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._outdir: str | None = None

    def _ensure_process(self) -> subprocess.Popen:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            return proc
        # stderr -> DEVNULL: Piper logs a line per utterance there, and an unread stderr
        # pipe would fill its buffer and block the process. bufsize=0 so our writes are
        # delivered immediately rather than sitting in a Python-side buffer.
        if self._outdir is None:
            self._outdir = tempfile.mkdtemp(prefix="transcibio_piper_")
        try:
            proc = subprocess.Popen(
                [self._bin, "--model", self._model, "--output_dir", self._outdir],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except FileNotFoundError as exc:
            raise StreamingTtsUnavailable("Piper binary disappeared.") from exc
        self._proc = proc
        return proc

    def synthesize_pcm(self, text: str) -> bytes:
        # Piper consumes one utterance per stdin line, so collapse all whitespace into
        # single spaces to keep it on one line. Blank input produces no WAV path, which
        # would block the read forever — return early instead.
        line = " ".join(text.split())
        if not line:
            return b""
        with self._lock:
            proc = self._ensure_process()
            assert proc.stdin is not None and proc.stdout is not None
            # Watchdog: if Piper wedges and never prints a path, kill it so readline()
            # returns EOF instead of blocking the turn forever.
            watchdog = threading.Timer(_PIPER_SYNTH_TIMEOUT_SECONDS, proc.kill)
            watchdog.start()
            try:
                proc.stdin.write((line + "\n").encode("utf-8"))
                proc.stdin.flush()
                raw_path = proc.stdout.readline()
            except (BrokenPipeError, OSError) as exc:
                self._reset_process()
                raise StreamingTtsError("Piper process write/read failed.") from exc
            finally:
                watchdog.cancel()
            if not raw_path:
                # EOF: the process exited (crashed on this input or was killed).
                self._reset_process()
                raise StreamingTtsError("Piper produced no audio (process exited).")
            wav_path = raw_path.decode("utf-8").strip()
            try:
                return _read_wav_pcm(wav_path)
            except (OSError, wave.Error) as exc:
                raise StreamingTtsError(f"Piper output unreadable: {exc}") from exc
            finally:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

    def _reset_process(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass

    def close(self) -> None:
        """Terminate the Piper process and remove its temp output directory."""
        with self._lock:
            self._reset_process()
            if self._outdir:
                shutil.rmtree(self._outdir, ignore_errors=True)
                self._outdir = None

    def __del__(self) -> None:  # best-effort; the OS reclaims the child on app exit
        try:
            self.close()
        except Exception:
            pass


class KokoroStreamingEngine:
    """English TTS via kokoro-onnx (in-process). Converts float32 samples to int16 PCM."""

    name = "kokoro"

    def __init__(
        self,
        *,
        model_path: str,
        voices_path: str,
        voice: str = "af_sarah",
        lang: str = "en-us",
    ) -> None:
        if not Path(model_path).exists():
            raise StreamingTtsUnavailable(f"Kokoro model not found: {model_path}")
        if not Path(voices_path).exists():
            raise StreamingTtsUnavailable(f"Kokoro voices not found: {voices_path}")
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise StreamingTtsUnavailable("kokoro-onnx is not installed.") from exc
        self._kokoro = Kokoro(model_path, voices_path)
        self.voice = voice
        self.lang = lang
        self.language = lang.split("-")[0].lower()  # "en-us" -> "en"
        self.sample_rate = _KOKORO_SAMPLE_RATE

    def synthesize_pcm(self, text: str) -> bytes:
        if not text.strip():
            return b""
        import numpy as np

        try:
            samples, sample_rate = self._kokoro.create(
                text, voice=self.voice, speed=1.0, lang=self.lang
            )
        except Exception as exc:  # kokoro raises bare exceptions on bad input
            raise StreamingTtsError(f"Kokoro synthesis failed: {exc}") from exc
        self.sample_rate = int(sample_rate)
        clipped = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
        return (clipped * 32767.0).astype("<i2").tobytes()


def build_streaming_engine(name: str, *, data_root: Path) -> StreamingTtsEngine:
    """Construct an engine by name, resolving model paths from env or ``data_root``."""
    key = name.strip().lower()
    models = data_root / "models" / "tts"
    if key == "piper":
        return PiperStreamingEngine(
            piper_bin=os.getenv("TRANSCIBIO_PIPER_BIN")
            or str(data_root / "bin" / "piper" / "piper.exe"),
            model_path=os.getenv("TRANSCIBIO_PIPER_MODEL")
            or str(models / "piper" / "de_DE-thorsten-high.onnx"),
        )
    if key == "kokoro":
        return KokoroStreamingEngine(
            model_path=os.getenv("TRANSCIBIO_KOKORO_MODEL")
            or str(models / "kokoro" / "kokoro-v1.0.onnx"),
            voices_path=os.getenv("TRANSCIBIO_KOKORO_VOICES")
            or str(models / "kokoro" / "voices-v1.0.bin"),
            voice=os.getenv("TRANSCIBIO_KOKORO_VOICE") or "af_sarah",
        )
    raise StreamingTtsUnavailable(f"Unknown TTS engine: {name!r}")


class VoiceEngineRegistry:
    """Lazily builds and caches engines so expensive model loads happen once."""

    def __init__(self, data_root: Path) -> None:
        self._data_root = data_root
        self._engines: dict[str, StreamingTtsEngine] = {}

    def get(self, name: str) -> StreamingTtsEngine:
        key = name.strip().lower()
        engine = self._engines.get(key)
        if engine is None:
            engine = build_streaming_engine(key, data_root=self._data_root)
            self._engines[key] = engine
        return engine
