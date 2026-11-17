from types import SimpleNamespace

import pytest

from backend.app.services import stt


@pytest.fixture(autouse=True)
def _clear_stt_env(monkeypatch):
    monkeypatch.delenv("TRANSCIBIO_STT_DEVICE", raising=False)
    monkeypatch.delenv("TRANSCIBIO_STT_COMPUTE_TYPE", raising=False)


def _fake_gpus(monkeypatch, count: int) -> None:
    monkeypatch.setattr(stt, "_cuda_device_count", lambda: count)


def test_auto_falls_back_to_cpu_int8_without_cuda(monkeypatch):
    _fake_gpus(monkeypatch, 0)

    assert stt.resolve_stt_runtime() == ("cpu", "int8")


def test_auto_uses_cuda_float16_when_gpu_visible(monkeypatch):
    _fake_gpus(monkeypatch, 1)

    assert stt.resolve_stt_runtime() == ("cuda", "float16")


def test_env_auto_value_still_detects(monkeypatch):
    _fake_gpus(monkeypatch, 0)
    monkeypatch.setenv("TRANSCIBIO_STT_DEVICE", "auto")

    assert stt.resolve_stt_runtime() == ("cpu", "int8")


def test_env_overrides_auto_detection(monkeypatch):
    _fake_gpus(monkeypatch, 1)
    monkeypatch.setenv("TRANSCIBIO_STT_DEVICE", "cpu")
    assert stt.resolve_stt_runtime() == ("cpu", "int8")

    monkeypatch.setenv("TRANSCIBIO_STT_COMPUTE_TYPE", "float32")
    assert stt.resolve_stt_runtime() == ("cpu", "float32")


def test_explicit_arguments_win_over_env(monkeypatch):
    _fake_gpus(monkeypatch, 0)
    monkeypatch.setenv("TRANSCIBIO_STT_DEVICE", "cpu")
    monkeypatch.setenv("TRANSCIBIO_STT_COMPUTE_TYPE", "int8")

    assert stt.resolve_stt_runtime("cuda", "float16") == ("cuda", "float16")


class _FakeTranscriber:
    """Stands in for both `WhisperModel` and `BatchedInferencePipeline`; records calls."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def transcribe(self, path, **kwargs):
        self.calls.append(kwargs)
        segment = SimpleNamespace(text=" Hallo Welt ", start=0.0, end=1.0, words=[])
        return iter([segment]), SimpleNamespace(language="de", language_probability=0.99)


def _install_fake_loaders(monkeypatch):
    """Fake both loaders; returns {loader name: [(model, device, compute)]} and the fake."""
    transcriber = _FakeTranscriber()
    loads: dict[str, list[tuple[str, str, str]]] = {"sequential": [], "batched": []}

    def make_loader(kind: str):
        def loader(model_name: str, device: str, compute_type: str):
            loads[kind].append((model_name, device, compute_type))
            return transcriber

        return loader

    monkeypatch.setattr(stt, "_load_faster_whisper_model", make_loader("sequential"))
    monkeypatch.setattr(stt, "_load_batched_pipeline", make_loader("batched"))
    return loads, transcriber


def _audio(tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"RIFF")
    return audio


def test_default_client_loads_model_on_resolved_runtime(monkeypatch, tmp_path):
    # The voice-command router builds `FasterWhisperSttClient()` with no arguments; on a
    # machine without CUDA (e.g. aarch64) it must load on CPU instead of failing on "cuda".
    _fake_gpus(monkeypatch, 0)
    loads, transcriber = _install_fake_loaders(monkeypatch)

    result = stt.FasterWhisperSttClient().transcribe_file(_audio(tmp_path), mode="command")

    assert loads == {"sequential": [("small", "cpu", "int8")], "batched": []}
    assert "batch_size" not in transcriber.calls[0]  # short commands gain nothing from batching
    assert result.text == "Hallo Welt"
    assert result.detected_language == "de"


def test_meeting_mode_uses_batched_pipeline_with_default_chunks(monkeypatch, tmp_path):
    _fake_gpus(monkeypatch, 1)
    loads, transcriber = _install_fake_loaders(monkeypatch)

    result = stt.FasterWhisperSttClient().transcribe_file(_audio(tmp_path), mode="meeting")

    assert loads == {"sequential": [], "batched": [("medium", "cuda", "float16")]}
    assert transcriber.calls[0]["batch_size"] == 8
    assert transcriber.calls[0]["word_timestamps"] is True  # assembly splits chunks by words
    # `without_timestamps=False` drops short utterances at chunk boundaries.
    assert "without_timestamps" not in transcriber.calls[0]
    assert result.text == "Hallo Welt"
