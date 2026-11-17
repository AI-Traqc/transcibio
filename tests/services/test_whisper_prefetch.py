from backend.app.services.stt import FasterWhisperSttClient
from backend.app.services.whisper_prefetch import (
    PrefetchResult,
    prefetch_whisper_models,
    preset_model_names,
)


class FakeDownloader:
    """Stands in for faster_whisper.download_model: a set of cached models, optional failures."""

    def __init__(self, cached=(), failing=()):
        self.cached = set(cached)
        self.failing = set(failing)
        self.downloads: list[str] = []

    def __call__(self, name, local_files_only=False):
        if local_files_only:
            if name not in self.cached:
                raise FileNotFoundError(name)
            return f"/cache/{name}"
        if name in self.failing:
            raise ConnectionError("offline")
        self.downloads.append(name)
        self.cached.add(name)
        return f"/cache/{name}"


def test_preset_model_names_covers_every_preset_once():
    assert preset_model_names() == ("small", "medium", "large-v3")


def test_preset_model_names_follows_custom_maps():
    client = FasterWhisperSttClient(
        meeting_model_map={"fast": "base", "balanced": "small", "quality": "small"},
        command_model_map={"fast": "tiny", "balanced": "base", "quality": "base"},
    )

    assert preset_model_names(client) == ("base", "small", "tiny")


def test_downloads_only_missing_models():
    downloader = FakeDownloader(cached={"small"})
    lines: list[str] = []

    result = prefetch_whisper_models(("small", "medium", "large-v3"), downloader, log=lines.append)

    assert result == PrefetchResult(cached=("small",), downloaded=("medium", "large-v3"))
    assert downloader.downloads == ["medium", "large-v3"]
    assert lines[0] == "  small: vorhanden"
    assert lines[-1] == "  large-v3: fertig"


def test_second_run_downloads_nothing():
    downloader = FakeDownloader()
    prefetch_whisper_models(("small", "medium"), downloader, log=lambda _: None)

    result = prefetch_whisper_models(("small", "medium"), downloader, log=lambda _: None)

    assert result == PrefetchResult(cached=("small", "medium"))
    assert downloader.downloads == ["small", "medium"]


def test_failed_download_is_reported_and_the_rest_continue():
    downloader = FakeDownloader(failing={"medium"})
    lines: list[str] = []

    result = prefetch_whisper_models(("small", "medium", "large-v3"), downloader, log=lines.append)

    assert result.failed == ("medium",)
    assert result.downloaded == ("small", "large-v3")
    assert "  medium: fehlgeschlagen (offline)" in lines


def test_no_models_is_a_no_op():
    assert prefetch_whisper_models((), FakeDownloader(), log=lambda _: None) == PrefetchResult()
