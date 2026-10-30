"""Speech-to-text via faster-whisper (CTranslate2 backend, CPU-friendly)."""
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_model():
    from faster_whisper import WhisperModel

    log.info(
        "loading faster-whisper model=%s compute=%s",
        settings.whisper_model,
        settings.whisper_compute_type,
    )
    return WhisperModel(
        settings.whisper_model,
        device="cpu",
        compute_type=settings.whisper_compute_type,
    )


def transcribe_file(path: Path) -> dict:
    """Transcribe an audio file. Returns {text, language, duration_sec}."""
    model = _get_model()
    segments, info = model.transcribe(
        str(path),
        # An empty WHISPER_LANGUAGE means auto-detect, like leaving it unset;
        # faster-whisper rejects "" as a language code.
        language=settings.whisper_language or None,
        beam_size=1,
        vad_filter=True,
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return {
        "text": text,
        "language": info.language,
        "duration_sec": info.duration,
    }
