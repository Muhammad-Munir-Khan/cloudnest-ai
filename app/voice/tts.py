"""Text-to-speech with two backends: Piper (offline) and Edge TTS (online).

Backend chosen by settings.tts_backend: "piper" or "edge".
Edge backend supports per-language neural voices via settings.edge_tts_voice_by_lang.

Text is sanitized before synthesis: markdown is stripped, symbols are spoken
out (≈ -> "approximately", ° -> "degrees", % -> "percent"), and CJK/full-width
punctuation is normalized to ASCII. Edge TTS in particular returns
NoAudioReceived when handed markup or certain punctuation, so cleaning is
required, not cosmetic. A single retry guards against transient Edge failures.
"""
import asyncio
import io
import re
import unicodedata
import urllib.request
import wave
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


# =============================================================================
# Text sanitization (shared by both backends)
# =============================================================================

# Symbols / punctuation normalized to spoken or safe equivalents.
_TTS_REPLACEMENTS = {
    # Math / units / general symbols
    "≈": " approximately ",
    "~": " approximately ",
    "°": " degrees ",
    "℃": " degrees ",      # single-char degree-Celsius (common in CJK text)
    "℉": " degrees ",
    "%": " percent ",
    "‰": " per mille ",
    "&": " and ",
    "@": " at ",
    "#": " ",
    "*": " ",
    "_": " ",
    "`": " ",
    "|": " ",
    "<": " ",
    ">": " ",
    "^": " ",
    "=": " equals ",
    "+": " plus ",
    "—": ", ",            # em dash
    "–": ", ",            # en dash
    "•": " ",
    "·": " ",
    "・": " ",
    # CJK / full-width punctuation -> ASCII + space
    "，": ", ",
    "。": ". ",
    "、": ", ",
    "：": ": ",
    "；": "; ",
    "！": "! ",
    "？": "? ",
    "（": " ",
    "）": " ",
    "【": " ",
    "】": " ",
    "《": " ",
    "》": " ",
    "「": " ",
    "」": " ",
    "『": " ",
    "』": " ",
    "～": " to ",          # full-width tilde (ranges, e.g. 21.6～33.0)
    "〜": " to ",          # wave dash
    "．": ". ",            # full-width period
    "　": " ",            # ideographic (full-width) space
}


def _clean_text_for_tts(text: str) -> str:
    """Make arbitrary assistant text safe and natural for TTS synthesis.

    Steps: strip markdown structure, drop code, normalize symbols and
    CJK/full-width punctuation, remove leftover control/format characters,
    then collapse whitespace. Returns "" if nothing speakable remains.
    """
    if not text:
        return ""

    t = text

    # 1. Remove fenced code blocks and inline code entirely (unspeakable).
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"~~~[\s\S]*?~~~", " ", t)

    # 2. Markdown links [label](url) -> label ; images ![alt](url) -> alt
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)

    # 3. Markdown table pipes and leading list markers.
    t = re.sub(r"(?m)^\s*[-*+•]\s+", " ", t)
    t = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", " ", t)   # ATX headings
    t = re.sub(r"(?m)^\s*>\s?", " ", t)            # blockquotes

    # 4. Symbol / punctuation normalization.
    for sym, word in _TTS_REPLACEMENTS.items():
        t = t.replace(sym, word)

    # 5. Drop any remaining Unicode control/format characters (category C*),
    #    which Edge can choke on, while keeping normal letters, marks, numbers,
    #    punctuation, symbols and separators.
    cleaned_chars = []
    for ch in t:
        if ch in "\n\r\t":
            cleaned_chars.append(" ")
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("C"):   # Cc, Cf, Cs, Co, Cn -> control/format/etc.
            continue
        cleaned_chars.append(ch)
    t = "".join(cleaned_chars)

    # 6. Collapse whitespace.
    t = re.sub(r"\s+", " ", t).strip()

    # 7. Guard: if only punctuation/symbols survive, treat as empty.
    if not re.search(r"[^\W_]", t, flags=re.UNICODE):
        return ""

    return t


# =============================================================================
# Edge TTS backend (Microsoft cloud, high-quality, requires internet)
# =============================================================================

def _resolve_edge_voice(language: str) -> str:
    """Pick the right Edge TTS voice for the given language code.

    Falls back to the configured default English voice for unknown codes.
    """
    voice_map = settings.edge_tts_voice_by_lang
    if language and language in voice_map:
        return voice_map[language]
    return settings.edge_tts_voice


def _edge_stream_once(clean_text: str, voice: str) -> bytes:
    """Single synthesis attempt. Returns MP3 bytes (may be empty)."""
    import edge_tts

    async def _run() -> bytes:
        communicate = edge_tts.Communicate(clean_text, voice=voice)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    return asyncio.run(_run())


def _synthesize_edge(text: str, language: str = "en") -> bytes:
    """Use Microsoft Edge's neural voices via edge-tts.

    NOTE: edge-tts uses an undocumented Microsoft API. Free, no key, but
    Microsoft could change or revoke access at any time. Returns MP3 bytes.
    """
    try:
        import edge_tts  # noqa: F401  (import-checked here for a clear error)
    except ImportError as e:
        raise RuntimeError(
            "edge-tts is not installed. Run: pip install edge-tts"
        ) from e

    voice = _resolve_edge_voice(language)
    clean = _clean_text_for_tts(text)
    if not clean:
        raise RuntimeError("No speakable text after cleaning for TTS.")

    log.debug(
        "Edge TTS synthesizing language=%s voice=%s clean_len=%d",
        language, voice, len(clean),
    )

    # One retry: Edge occasionally returns NoAudioReceived transiently even
    # for valid input.
    last_err: Exception | None = None
    for attempt in (1, 2):
        try:
            audio = _edge_stream_once(clean, voice)
        except Exception as e:  # includes edge_tts.exceptions.NoAudioReceived
            last_err = e
            log.warning("Edge TTS attempt %d failed: %s", attempt, e)
            continue
        if audio:
            return audio
        last_err = RuntimeError("Edge returned empty audio")
        log.warning("Edge TTS attempt %d produced no audio", attempt)

    raise RuntimeError(
        f"Edge TTS produced no audio (voice={voice}, language={language}). "
        f"Last error: {last_err}"
    )


# =============================================================================
# Piper backend (local, offline, English-only with the bundled voice)
# =============================================================================

VOICES_DIR = Path.home() / ".cache" / "piper-voices"
VOICE_BASE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/"
)
VOICE_FILES = {
    "en_US-lessac-medium.onnx": VOICE_BASE_URL + "en_US-lessac-medium.onnx",
    "en_US-lessac-medium.onnx.json": VOICE_BASE_URL + "en_US-lessac-medium.onnx.json",
}


def _ensure_piper_voice() -> Path:
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = VOICES_DIR / "en_US-lessac-medium.onnx"
    json_path = VOICES_DIR / "en_US-lessac-medium.onnx.json"
    for name, url in VOICE_FILES.items():
        target = VOICES_DIR / name
        if target.exists() and target.stat().st_size > 0:
            continue
        log.info("downloading piper voice file %s", name)
        urllib.request.urlretrieve(url, target)
    if not onnx_path.exists() or not json_path.exists():
        raise RuntimeError("Failed to download Piper voice files")
    return onnx_path


@lru_cache(maxsize=1)
def _get_piper_voice():
    from piper import PiperVoice
    onnx = _ensure_piper_voice()
    return PiperVoice.load(str(onnx))


def _synthesize_piper(text: str) -> bytes:
    voice = _get_piper_voice()
    clean = _clean_text_for_tts(text)
    if not clean:
        raise RuntimeError("No speakable text after cleaning for TTS.")
    buf = io.BytesIO()

    if hasattr(voice, "synthesize_wav"):
        with wave.open(buf, "wb") as wav:
            voice.synthesize_wav(clean, wav)
        return buf.getvalue()

    if hasattr(voice, "synthesize"):
        chunks = list(voice.synthesize(clean))
        if not chunks:
            raise RuntimeError("Piper produced no audio chunks")
        first = chunks[0]
        sample_rate = getattr(first, "sample_rate", 22050)
        sample_width = getattr(first, "sample_width", 2)
        channels = getattr(first, "sample_channels", 1)
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(sample_width)
            wav.setframerate(sample_rate)
            for ch in chunks:
                data = getattr(ch, "audio_int16_bytes", None)
                if data is None:
                    data = getattr(ch, "audio", b"")
                if isinstance(data, memoryview):
                    data = bytes(data)
                wav.writeframes(data)
        return buf.getvalue()

    raise RuntimeError("Installed piper-tts has no recognized synthesis method.")


# =============================================================================
# Public API
# =============================================================================

def synthesize(text: str, language: str = "en") -> bytes:
    """Synthesize text → audio bytes (WAV for Piper, MP3 for Edge).

    The `language` parameter only affects the Edge backend, where it
    selects a matching neural voice. Piper uses its bundled English voice
    regardless — switch to Edge if you need multilingual TTS.
    """
    if not settings.enable_voice:
        raise RuntimeError("Voice features are disabled (settings.enable_voice).")

    backend = settings.tts_backend.lower()
    if backend == "edge":
        return _synthesize_edge(text, language=language)
    if backend == "piper":
        if language and language != "en":
            log.warning(
                "Piper backend only supports English; ignoring language=%s. "
                "Switch TTS_BACKEND=edge for multilingual support.",
                language,
            )
        return _synthesize_piper(text)
    raise ValueError(f"Unknown tts_backend: {settings.tts_backend!r}")


def get_media_type() -> str:
    """Return the MIME type the current backend produces."""
    return "audio/mpeg" if settings.tts_backend.lower() == "edge" else "audio/wav"
