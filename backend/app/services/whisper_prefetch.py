"""Download every faster-whisper model the Settings presets can pick.

The app otherwise downloads a model the first time a preset needs it, so switching to
"Quality" meant waiting for `large-v3`. The launchers run this once per start inside the
backend container (models land in the Hugging Face cache, `data/.hf_cache` in Docker):

    python -m backend.app.services.whisper_prefetch

Models already in the cache are skipped without network access. A failed download is
reported and the others continue; the app still downloads a missing model on first use.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from backend.app.services.stt import FasterWhisperSttClient

# faster_whisper.download_model(name, local_files_only=...) -> local path
Downloader = Callable[..., str]


@dataclass(frozen=True)
class PrefetchResult:
    cached: tuple[str, ...] = ()
    downloaded: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()


def preset_model_names(client: FasterWhisperSttClient | None = None) -> tuple[str, ...]:
    """Models used by the meeting and voice-command presets, each once, in preset order."""
    client = client or FasterWhisperSttClient()
    names = (*client.meeting_model_map.values(), *client.command_model_map.values())
    return tuple(dict.fromkeys(names))


def prefetch_whisper_models(
    models: Iterable[str],
    download: Downloader,
    log: Callable[[str], None] = print,
) -> PrefetchResult:
    """Download each model unless it's cached. Messages are German ASCII (launcher output)."""
    cached: list[str] = []
    downloaded: list[str] = []
    failed: list[str] = []
    for name in models:
        try:
            download(name, local_files_only=True)
        except Exception:
            pass
        else:
            cached.append(name)
            log(f"  {name}: vorhanden")
            continue
        log(f"  {name}: wird heruntergeladen ...")
        try:
            download(name)
        except Exception as exc:
            failed.append(name)
            log(f"  {name}: fehlgeschlagen ({exc})")
        else:
            downloaded.append(name)
            log(f"  {name}: fertig")
    return PrefetchResult(tuple(cached), tuple(downloaded), tuple(failed))


def main() -> int:
    from faster_whisper import download_model

    result = prefetch_whisper_models(
        preset_model_names(), download_model, log=lambda line: print(line, flush=True)
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
