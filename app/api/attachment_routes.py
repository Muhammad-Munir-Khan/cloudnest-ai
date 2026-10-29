"""Attachment endpoints: extract text, optionally persist to docs. Auth required.

Only the extracted text is returned to the client; the raw upload is not kept
on disk (it used to be copied to data/repl_workspace/<user_hex>/ for
python_repl/csv_reader tools that no longer exist).

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
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.api.errors import internal_error
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


@router.post("/extract", response_model=ExtractResponse)
async def extract(
    file: UploadFile = File(...),
    persist: bool = Form(False),
    user: User = Depends(current_active_user),
):
    """Extract text from an uploaded file. Optionally persist into data/docs.

    The raw bytes are only held in memory for extraction; nothing is written
    to disk unless persist=True (superusers only).

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

    # PDF parsing and vision OCR are blocking (CPU + provider HTTP calls).
    try:
        result = await run_in_threadpool(extract_attachment, file.filename, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        # Provider/OCR problems (missing key or model, upstream error). The
        # message may contain provider responses, so it is only logged.
        raise internal_error(
            "Text extraction is temporarily unavailable", e, status_code=503
        ) from e
    except Exception as e:
        raise internal_error("Extraction failed", e) from e

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