"""Voice endpoints: STT (upload audio) and TTS (text -> audio). Auth required."""
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.api.errors import internal_error
from app.api.uploads import read_upload_limited
from app.core.auth import current_active_user
from app.core.config import settings
from app.core.logging import get_logger
from app.core.schemas import TranscribeResponse, TTSRequest
from app.models.user import User

log = get_logger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

ALLOWED_AUDIO_EXT = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"}
# Mic recordings are small; this only stops abusive uploads.
MAX_AUDIO_BYTES = 25 * 1024 * 1024


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    file: UploadFile = File(...),
    user: User = Depends(current_active_user),
):
    if not settings.enable_voice:
        raise HTTPException(status_code=503, detail="Voice features are disabled")

    suffix = Path(file.filename or "audio.wav").suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format {suffix}. "
                   f"Allowed: {sorted(ALLOWED_AUDIO_EXT)}",
        )

    data = await read_upload_limited(file, MAX_AUDIO_BYTES)
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        from app.voice.stt import transcribe_file
        # Whisper inference is CPU-bound; keep it off the event loop.
        result = await run_in_threadpool(transcribe_file, tmp_path)
    except Exception as e:
        raise internal_error("Transcription failed", e) from e
    finally:
        tmp_path.unlink(missing_ok=True)

    return TranscribeResponse(**result)


@router.post("/tts")
def tts(req: TTSRequest, user: User = Depends(current_active_user)):
    if not settings.enable_voice:
        raise HTTPException(status_code=503, detail="Voice features are disabled")
    log.info(
        "TTS request: backend=%s language=%s text_len=%d",
        settings.tts_backend, req.language, len(req.text or ""),
    )
    try:
        from app.voice.tts import get_media_type, synthesize
        audio_bytes = synthesize(req.text, language=req.language)
        media_type = get_media_type()
    except Exception as e:
        # The full traceback (Edge API failure, Piper voice download, etc.)
        # goes to the server log under the reference id.
        raise internal_error("Speech synthesis failed", e) from e

    ext = "mp3" if media_type == "audio/mpeg" else "wav"
    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="speech.{ext}"'},
    )
