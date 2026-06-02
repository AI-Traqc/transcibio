import json
from pathlib import Path

from backend.app.services.tts_streaming import (
    _piper_language,
    _piper_sample_rate,
    _read_piper_config,
)


def _write_config(tmp_path: Path, payload: dict) -> str:
    model_path = tmp_path / "voice.onnx"
    Path(f"{model_path}.json").write_text(json.dumps(payload), encoding="utf-8")
    return str(model_path)


def test_piper_language_reads_family_from_config(tmp_path: Path):
    model_path = _write_config(
        tmp_path, {"language": {"code": "de_DE", "family": "de"}, "audio": {"sample_rate": 22050}}
    )
    config = _read_piper_config(model_path)
    assert _piper_language(config) == "de"
    assert _piper_sample_rate(config) == 22050


def test_piper_language_falls_back_to_code(tmp_path: Path):
    model_path = _write_config(tmp_path, {"language": {"code": "en_US"}})
    assert _piper_language(_read_piper_config(model_path)) == "en"


def test_piper_language_defaults_to_german_when_missing(tmp_path: Path):
    model_path = _write_config(tmp_path, {"audio": {"sample_rate": 16000}})
    config = _read_piper_config(model_path)
    assert _piper_language(config) == "de"
    assert _piper_sample_rate(config) == 16000


def test_read_piper_config_missing_file_is_empty():
    config = _read_piper_config("does-not-exist.onnx")
    assert config == {}
    # Defaults hold when the config is unreadable.
    assert _piper_language(config) == "de"
    assert _piper_sample_rate(config) == 22050
