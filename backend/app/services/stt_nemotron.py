"""NVIDIA Nemotron 3.5 Transcribe as an optional second transcription engine.

One request to a vLLM server (OpenAI-compatible `/v1/chat/completions`) returns the
transcript with speaker tags plus word timestamps (`ctc_timestamps`). The engine maps that
single response to the same `(SttResult, DiarizationAttemptResult)` pair the
Whisper + pyannote path produces, so `TranscriptAssemblyService` treats both alike.

Deliberately **no fallback** to Whisper: if Nemotron is selected and its server is down,
the job fails with a clear message (a silent fallback would spoil the comparison).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from backend.app.services.diarization import DiarizationAttemptResult, DiarizationSpeakerSegment
from backend.app.services.stt import (
    LanguageHint,
    SttError,
    SttPreset,
    SttResult,
    SttSegment,
    SttWord,
)

_LOGGER = logging.getLogger(__name__)

ENGINE_NAME = "nemotron"
DEFAULT_URL = "http://127.0.0.1:8010/v1/chat/completions"
DEFAULT_MODEL = "nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-NVFP4"
DEFAULT_TIMEOUT_SECONDS = 1800.0
# The model accepts recordings up to one hour per request; chunking is out of scope.
MAX_AUDIO_MS = 60 * 60 * 1000

# Prompts from the model card ("Prompt Guide"). The speaker prompt lists 4 tags as
# documented; training mixtures had up to 8 speakers.
SPEAKER_PROMPT = (
    "Transcribe this audio with punctuation and capitalization. "
    "Include all spoken words and verbal fillers. "
    "Write numbers in their standard written form. "
    "Put speaker tags <spk:0> <spk:1> <spk:2> <spk:3> on the transcription."
)
# Without diarization: the card's readable-transcript prompt. Punctuation matters because
# TranscriptAssemblyService splits sentences on it.
PLAIN_PROMPT = (
    "Audio transcription. Language: as spoken. Wording: verbatim, including fillers and "
    "repetitions. Formatting: punctuation and capitalization. Output: transcript only."
)

# (url, json_body, timeout_seconds) -> parsed JSON response. Injected in tests.
Transport = Callable[[str, dict[str, Any], float], dict[str, Any]]


class NemotronError(SttError):
    """Nemotron request or response failed; the transcription job fails with this message."""


@dataclass(frozen=True)
class NemotronConfig:
    url: str
    model: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> NemotronConfig:
        raw_timeout = (os.getenv("TRANSCIBIO_NEMOTRON_TIMEOUT_SECONDS") or "").strip()
        try:
            timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT_SECONDS
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS
        return cls(
            url=(os.getenv("TRANSCIBIO_NEMOTRON_URL") or DEFAULT_URL).strip(),
            model=(os.getenv("TRANSCIBIO_NEMOTRON_MODEL") or DEFAULT_MODEL).strip(),
            timeout_seconds=timeout,
        )

    @property
    def models_url(self) -> str:
        """`.../v1/chat/completions` -> `.../v1/models` (reachability check)."""
        base = self.url.split("/v1/", 1)[0]
        return f"{base}/v1/models"


def _urllib_transport(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise NemotronError(f"Nemotron server returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise NemotronError(
            f"Nemotron server not reachable at {url} ({exc}). Start it with "
            "COMPOSE_PROFILES=nemotron or switch the "
            "transcription engine back to Whisper + pyannote in Settings."
        ) from exc
    except json.JSONDecodeError as exc:
        raise NemotronError("Nemotron server returned invalid JSON.") from exc


def check_nemotron_server(config: NemotronConfig | None = None) -> dict[str, Any]:
    """Reachability for Settings/health: `GET /v1/models`, like the Ollama tags check."""
    config = config or NemotronConfig.from_env()
    status: dict[str, Any] = {"models_url": config.models_url, "model": config.model}
    try:
        with urllib.request.urlopen(config.models_url, timeout=2) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
        served = [str(item.get("id")) for item in data.get("data", []) if item.get("id")]
        status.update(reachable=True, served_models=served)
    except Exception as exc:  # noqa: BLE001 - any failure means "not reachable"
        status.update(reachable=False, served_models=[], error=str(exc))
    return status


def encode_audio_as_flac(audio_path: Path, *, ffmpeg_path: str | None = None) -> bytes:
    """16 kHz mono FLAC: a 1-hour WAV is ~115 MB (~154 MB base64), close to the server's
    180 MB limit; FLAC is a fraction of that."""
    ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not ffmpeg:
        raise NemotronError("FFmpeg is required to prepare audio for Nemotron.")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "audio.flac"
        command = [
            ffmpeg, "-y", "-loglevel", "error", "-i", str(audio_path),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac", str(target),
        ]  # fmt: skip
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not target.exists():
            raise NemotronError(
                f"FFmpeg could not convert the audio for Nemotron: {result.stderr.strip()}"
            )
        return target.read_bytes()


def build_request_body(
    *, model: str, audio_flac: bytes, with_speakers: bool, timestamps: bool = True
) -> dict[str, Any]:
    """Request as on the model card. Its `extra_body` fields are top-level JSON here.

    `timestamps=False` (voice commands) skips the word alignment, which short clips don't need.
    """
    audio_b64 = base64.b64encode(audio_flac).decode("ascii")
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": SPEAKER_PROMPT if with_speakers else PLAIN_PROMPT},
                    {
                        "type": "audio_url",
                        "audio_url": {"url": f"data:audio/flac;base64,{audio_b64}"},
                    },
                ],
            }
        ],
        "temperature": 0,
        "top_p": 1.0,
        # A dense one-hour conversation can need ~20k output tokens.
        "max_tokens": 32768,
        "seed": 0,
        "chat_template_kwargs": {"enable_thinking": False},
        "skip_special_tokens": False,  # keep the <spk:N> tags
        "spaces_between_special_tokens": False,
        **({"mm_processor_kwargs": {"capture_ctc_timestamps": True}} if timestamps else {}),
    }


_SPEAKER_TAG_RE = re.compile(r"<spk:\d+>")


def text_from_response(data: dict[str, Any]) -> str:
    """Plain transcript text from `choices[0].message.content` (speaker tags removed)."""
    try:
        content = data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise NemotronError("Nemotron returned an unexpected response.") from exc
    return " ".join(_SPEAKER_TAG_RE.sub(" ", str(content)).split())


def _speaker_key(tag: Any) -> str:
    """Nemotron speaker tag ("0", 1, ...) -> the pyannote-style key the app already shows."""
    try:
        return f"SPEAKER_{int(tag):02d}"
    except (TypeError, ValueError):
        return "SPEAKER_00"


def parse_response(
    data: dict[str, Any],
    *,
    model_name: str,
    preset: SttPreset,
    with_speakers: bool,
    language: str | None = None,
) -> tuple[SttResult, DiarizationAttemptResult]:
    """Map one Nemotron response to `(SttResult, DiarizationAttemptResult)`.

    Response shape (vLLM + NeMo Speech): a top-level `ctc_timestamps`
    with `words` = [{word, start, end, speaker}] (seconds; words carry punctuation and
    capitalization, so the sentence split works), `diarization` = [{speaker, start, end}],
    `speaker_tag_to_diarization_speaker` = {"0": 0, ...} and `error`.

    Speaker source: the per-word `speaker` tags. They match the tagged transcript text and
    have no gaps, unlike the `diarization` segments. Speaker segments are runs of consecutive
    same-speaker words, so `TranscriptAssemblyService` assigns sentences exactly as tagged.
    """
    alignment = data.get("ctc_timestamps")
    if not isinstance(alignment, dict):
        raise NemotronError(
            "Nemotron response has no word timestamps (ctc_timestamps). Start the server "
            "with the ctc_timestamp_middleware and --trust-request-mm-kwargs."
        )
    if alignment.get("error"):
        raise NemotronError(f"Nemotron word alignment failed: {alignment['error']}")

    turns: list[tuple[str, list[SttWord]]] = []
    for item in alignment.get("words") or []:
        text = str(item.get("word") or "").strip()
        start, end = item.get("start"), item.get("end")
        if not text or start is None or end is None:
            continue
        word = SttWord(text=text, start_seconds=float(start), end_seconds=float(end))
        key = _speaker_key(item.get("speaker")) if with_speakers else "SPEAKER_00"
        if turns and turns[-1][0] == key:
            turns[-1][1].append(word)
        else:
            turns.append((key, [word]))
    if not turns:
        raise NemotronError("Nemotron returned an empty transcript.")

    segments = tuple(
        SttSegment(
            text=" ".join(w.text for w in words),
            start_seconds=words[0].start_seconds,
            end_seconds=words[-1].end_seconds,
            words=tuple(words),
        )
        for _, words in turns
    )
    stt_result = SttResult(
        text=" ".join(segment.text for segment in segments),
        segments=segments,
        detected_language=language,  # the model has no language output ("as spoken")
        detected_language_probability=None,
        model_name=model_name,
        mode="meeting",
        preset=preset,
    )
    if not with_speakers:
        return stt_result, DiarizationAttemptResult(segments=(), used=False, provider=ENGINE_NAME)
    diarization = DiarizationAttemptResult(
        segments=tuple(
            DiarizationSpeakerSegment(
                start_seconds=float(words[0].start_seconds or 0.0),
                end_seconds=float(words[-1].end_seconds or 0.0),
                speaker_key=key,
            )
            for key, words in turns
        ),
        used=True,
        provider=ENGINE_NAME,
    )
    return stt_result, diarization


class NemotronTranscriptionEngine:
    """Transcription engine backed by a Nemotron 3.5 Transcribe vLLM server."""

    name = ENGINE_NAME

    def __init__(
        self,
        *,
        config: NemotronConfig | None = None,
        transport: Transport | None = None,
        audio_encoder: Callable[[Path], bytes] | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or _urllib_transport
        self._audio_encoder = audio_encoder or encode_audio_as_flac

    def transcribe(
        self,
        audio_path: Path,
        *,
        language_hint: LanguageHint,
        preset: SttPreset,
        diarization_enabled: bool,
        duration_ms: int | None,
        on_stt_complete: Callable[[SttResult], None] | None = None,
    ) -> tuple[SttResult, DiarizationAttemptResult]:
        if duration_ms is not None and duration_ms > MAX_AUDIO_MS:
            minutes = duration_ms / 60000
            raise NemotronError(
                f"Recording is {minutes:.0f} min long; Nemotron accepts at most 60 min per "
                "request. Use Whisper + pyannote for longer recordings."
            )
        config = self._config or NemotronConfig.from_env()
        body = build_request_body(
            model=config.model,
            audio_flac=self._audio_encoder(audio_path),
            with_speakers=diarization_enabled,
        )
        started = time.perf_counter()
        data = self._transport(config.url, body, config.timeout_seconds)
        stt_result, diarization = parse_response(
            data,
            model_name=config.model,
            preset=preset,
            with_speakers=diarization_enabled,
            # No language parameter or output: the model transcribes "as spoken".
            language=None if language_hint == "auto" else language_hint,
        )
        _LOGGER.info(
            "[STT] engine=%s model=%s took %.1f s (transcript + speakers in one request)",
            self.name,
            config.model,
            time.perf_counter() - started,
        )
        if on_stt_complete is not None:
            on_stt_complete(stt_result)
        return stt_result, diarization

    def transcribe_text(self, audio_path: Path) -> tuple[str, str]:
        """Voice commands / voice mode: `(text, model_name)` for a short clip.

        Plain prompt, no speaker tags, no word alignment. No Whisper fallback: a down
        server raises `NemotronError` (an `SttError`), which the caller reports.
        """
        config = self._config or NemotronConfig.from_env()
        body = build_request_body(
            model=config.model,
            audio_flac=self._audio_encoder(audio_path),
            with_speakers=False,
            timestamps=False,
        )
        started = time.perf_counter()
        text = text_from_response(self._transport(config.url, body, config.timeout_seconds))
        _LOGGER.info(
            "[STT] engine=%s voice input took %.2f s", self.name, time.perf_counter() - started
        )
        return text, config.model


__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_URL",
    "ENGINE_NAME",
    "MAX_AUDIO_MS",
    "NemotronConfig",
    "NemotronError",
    "NemotronTranscriptionEngine",
    "build_request_body",
    "check_nemotron_server",
    "encode_audio_as_flac",
    "parse_response",
    "text_from_response",
]
