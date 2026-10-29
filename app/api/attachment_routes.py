"""Attachment endpoints: extract text, optionally persist to docs. Auth required.

Beyond text extraction, the raw uploaded file is also saved into the user's
per-user workspace folder (data/repl_workspace/<user_hex>/) so that the
python_repl and csv_reader tools can find it by its original filename in
subsequent agent turns.

Upload hardening (Phase 1):
  - Size cap enforced BEFORE extraction (413 instead of reading/parsing a huge
    body).
  - Extension allowlist — only the types the extractor actually supports.
  - Magic-byte signature check for binary types (PDF/PNG/JPEG/WEBP/GIF) so a
    file can't lie about its type via the extension. Text types (txt/md/csv/tsv)
    are validated by attempting a UTF-8/latin-1 decode in the extractor.
These run after auth and the empty-file check, so an unauthenticated or empty
request is rejected first.
"""
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.api.uploads import read_upload_limited
from app.core.auth import current_active_user
from app.core.config import settings
from app.core.logging import get_logger
from app.models.user import User
from app.rag.extraction import extract_attachment

log = get_logger(__name__)
router = APIRouter(prefix="/attachments", tags=["attachments"])

# --- Upload validation policy --------------------------------------------------

# 20 MB hard cap at the route (mirrors extraction.MAX_FILE_BYTES; enforced here
# first so we reject before doing any work).
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# Only the types the extractor supports. Keep in sync with extraction.py.
TEXT_EXTS = {".txt", ".md", ".csv", ".tsv"}
BINARY_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_EXTS = TEXT_EXTS | BINARY_EXTS

# Leading-byte signatures for the binary types we accept. A file whose bytes
# don't match its claimed extension is rejected — defends against a .pdf that's
# actually an executable, an image with a spoofed extension, etc.
def _sniff_ok(ext: str, data: bytes) -> bool:
    head = data[:16]
    if ext == ".pdf":
        return head.startswith(b"%PDF")
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".gif":
        return head.startswith((b"GIF87a", b"GIF89a"))
    if ext == ".webp":
        # RIFF....WEBP
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    # Text types have no reliable signature; the extractor validates by decoding.
    return True


def _validate_upload(filename: str, data: bytes) -> None:
    """Raise HTTPException if the upload violates size/type policy."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {len(data) / 1e6:.1f} MB (max {MAX_UPLOAD_BYTES / 1e6:.0f} MB)",
        )
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext or '(none)'}'. Allowed: {sorted(ALLOWED_EXTS)}",
        )
    if ext in BINARY_EXTS and not _sniff_ok(ext, data):
        raise HTTPException(
            status_code=400,
            detail=f"File content does not match its '{ext}' extension (failed signature check).",
        )


class ExtractResponse(BaseModel):
    filename: str
    text: str
    method: str
    pages_processed: int
    size_bytes: int
    char_count: int


def _sanitize_filename(name: str) -> str:
    """Strip directory components and unsafe characters from an uploaded
    filename so we can use it safely as a path inside the user's workspace.
    """
    # Path(name).name drops any directory parts (defense against ../../).
    base = Path(name).name
    # Replace anything that isn't alnum, dot, dash, underscore.
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in base)
    # Avoid pathological empty names.
    return safe or "upload.bin"


def _save_to_user_workspace(user: User, filename: str, data: bytes) -> Path | None:
    """Save the raw uploaded bytes into the user's repl_workspace folder so
    python_repl and csv_reader can find the file by name.

    Best-effort: if this fails (disk full, permissions, etc.) the request
    still succeeds because the extracted text is enough for most uses.
    """
    try:
        workspace = settings.data_dir / "repl_workspace" / user.id.hex
        workspace.mkdir(parents=True, exist_ok=True)
        target = workspace / _sanitize_filename(filename)
        target.write_bytes(data)
        log.info(
            "saved attachment %s to user workspace %s (%d bytes)",
            target.name, user.id.hex, len(data),
        )
        return target
    except Exception as e:
        log.warning("failed to save attachment to user workspace: %s", e)
        return None


@router.post("/extract", response_model=ExtractResponse)
async def extract(
    file: UploadFile = File(...),
    persist: bool = Form(False),
    user: User = Depends(current_active_user),
):
    """Extract text from an uploaded file. Optionally persist into data/docs.

    The raw file is ALWAYS also saved into the user's repl_workspace folder
    so python_repl and csv_reader can read it by filename.

    NOTE: `persist=True` re-indexes the SHARED corpus, which all users currently
    query. To prevent random users from polluting it, persist+reindex is now
    restricted to superusers.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")

    if persist and not user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Only admins can persist documents to the shared corpus. "
                   "Per-user document upload coming in Phase 2c.",
        )

    data = await read_upload_limited(file, MAX_UPLOAD_BYTES)
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    # Validate size + type + signature BEFORE doing any extraction work.
    _validate_upload(file.filename, data)

    # Save raw file to the user's private workspace BEFORE extraction so that
    # tools can find it even if extraction later fails. Best-effort.
    _save_to_user_workspace(user, file.filename, data)

    # PDF parsing and vision OCR are blocking (CPU + provider HTTP calls).
    try:
        result = await run_in_threadpool(extract_attachment, file.filename, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.exception("extraction failed")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")

    if persist:
        # Save the original file into data/docs and re-index.
        target = settings.docs_dir / Path(file.filename).name
        target.write_bytes(data)
        log.info("persisted attachment to %s", target)
        # Trigger background re-ingest. Synchronous is fine for small corpora.
        try:
            from app.rag.ingestion import ingest
            await run_in_threadpool(ingest)
        except Exception as e:
            log.warning("re-ingest after persist failed: %s", e)

    return ExtractResponse(
        filename=file.filename,
        text=result["text"],
        method=result["method"],
        pages_processed=result["pages_processed"],
        size_bytes=result["size_bytes"],
        char_count=len(result["text"]),
    )