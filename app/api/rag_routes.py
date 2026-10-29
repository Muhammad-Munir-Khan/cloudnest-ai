"""RAG endpoints — per-user document storage, ingestion, and retrieval."""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.api.errors import internal_error
from app.api.uploads import read_upload_limited
from app.core.auth import current_active_user
from app.core.logging import get_logger
from app.core.schemas import IngestResponse, QueryRequest, QueryResponse
from app.models.user import User
from app.rag.chain import rag_answer
from app.rag.collections import docs_dir_for
from app.rag.ingestion import (
    SUPPORTED_EXTENSIONS,
    delete_file_from_user,
    ingest,
    ingest_for_user,
    ingest_single_file_for_user,
    list_files_for_user,
)
from app.rag.user_context import set_current_user, reset_current_user

log = get_logger(__name__)
router = APIRouter(prefix="/rag", tags=["rag"])

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB


class DocumentInfo(BaseModel):
    filename: str
    size_bytes: int
    chunks_indexed: int


class UploadResponse(BaseModel):
    filename: str
    chunks_indexed: int
    message: str


# --- Query (per-user, scoped via contextvar) ----------------------------------

@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, user: User = Depends(current_active_user)):
    token = set_current_user(user.id)
    try:
        return rag_answer(req.question, top_k=req.top_k, language=req.language)
    except Exception as e:
        raise internal_error("RAG query failed", e) from e
    finally:
        reset_current_user(token)


# --- Per-user document management --------------------------------------------

@router.get("/documents", response_model=list[DocumentInfo])
def list_documents(user: User = Depends(current_active_user)):
    """List all documents the current user has uploaded + their indexing status."""
    try:
        return list_files_for_user(user.id)
    except Exception as e:
        raise internal_error("Listing documents failed", e) from e


@router.post("/documents", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(current_active_user),
):
    """Upload a document, save it to the user's folder, and ingest it.

    Synchronous: the request blocks until ingestion is complete (typically
    2-5s for small files, up to 30s for large PDFs).
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")

    # Sanitize: strip path components, keep only the basename.
    safe_name = Path(file.filename).name
    if not safe_name:
        raise HTTPException(status_code=400, detail="invalid filename")

    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {suffix}. "
                   f"Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    # Read with size cap (aborts as soon as the limit is crossed).
    data = await read_upload_limited(file, MAX_FILE_BYTES)
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    # Save to disk in the user's folder.
    target = docs_dir_for(user.id) / safe_name
    target.write_bytes(data)
    log.info("user %s uploaded %s (%d bytes)", user.id, safe_name, len(data))

    # Ingest just this file (does not wipe existing chunks). Parsing and
    # embedding are blocking, so run them off the event loop.
    try:
        result = await run_in_threadpool(ingest_single_file_for_user, user.id, target)
    except Exception as e:
        # Roll back the file if ingestion failed.
        target.unlink(missing_ok=True)
        raise internal_error("Ingestion failed", e, f"ingestion failed for {safe_name}") from e

    return UploadResponse(
        filename=safe_name,
        chunks_indexed=result["chunks"],
        message=f"Uploaded and indexed {safe_name} ({result['chunks']} chunks).",
    )


@router.delete("/documents/{filename}")
def delete_document(
    filename: str,
    user: User = Depends(current_active_user),
):
    """Delete a document — both the file on disk and its chunks in the index."""
    safe_name = Path(filename).name
    target = docs_dir_for(user.id) / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove chunks from the user's collection first.
    try:
        chunks_deleted = delete_file_from_user(user.id, safe_name)
    except Exception as e:
        raise internal_error(
            "Index cleanup failed", e, f"failed to delete chunks for {safe_name}"
        ) from e

    # Then remove the file.
    target.unlink()
    log.info("user %s deleted %s (%d chunks removed)", user.id, safe_name, chunks_deleted)
    return {
        "filename": safe_name,
        "chunks_deleted": chunks_deleted,
        "status": "deleted",
    }


@router.post("/reindex", response_model=IngestResponse)
def reindex_my_docs(user: User = Depends(current_active_user)):
    """Wipe and rebuild the current user's collection from the files on disk.

    Useful if their collection got into a bad state. Doesn't add new files —
    use POST /documents for that.
    """
    try:
        result = ingest_for_user(user.id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No documents to re-index.") from None
    except Exception as e:
        raise internal_error("Re-index failed", e) from e
    return IngestResponse(
        chunks_indexed=result["chunks"],
        files_processed=result["files"],
        message=f"Re-indexed {result['chunks']} chunks from {result['files']} files.",
    )


# --- Superuser-only legacy endpoint ------------------------------------------

@router.post("/ingest", response_model=IngestResponse)
def run_global_ingestion(user: User = Depends(current_active_user)):
    """Re-index data/docs/ (root) into a global 'documents' collection.

    Restricted to superusers. This is the old shared-corpus model — kept for
    backwards compat but no normal users hit it.
    """
    if not user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Only admins can trigger global re-ingestion. "
                   "Use POST /rag/documents to upload your own files.",
        )
    try:
        result = ingest()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No documents to ingest.") from None
    return IngestResponse(
        chunks_indexed=result["chunks"],
        files_processed=result["files"],
        message=f"Indexed {result['chunks']} chunks from {result['files']} files.",
    )