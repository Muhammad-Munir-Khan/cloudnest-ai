"""An empty WHISPER_LANGUAGE must mean auto-detect, not the language code "".

faster-whisper raises ValueError for "", which turned every /voice/transcribe
call into a 500 for a .env that had `WHISPER_LANGUAGE=` with no value.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.voice import stt


class _FakeModel:
    def __init__(self):
        self.language = "unset"

    def transcribe(self, _path, language=None, **_kwargs):
        self.language = language
        return iter([SimpleNamespace(text=" hello ")]), SimpleNamespace(language="en", duration=1.0)


@pytest.mark.parametrize("configured, expected", [("", None), (None, None), ("en", "en")])
def test_language_setting_is_passed_to_whisper(monkeypatch, configured, expected):
    model = _FakeModel()
    monkeypatch.setattr(stt, "_get_model", lambda: model)
    monkeypatch.setattr(settings, "whisper_language", configured)

    result = stt.transcribe_file(Path("audio.wav"))

    assert model.language == expected
    assert result["text"] == "hello"
