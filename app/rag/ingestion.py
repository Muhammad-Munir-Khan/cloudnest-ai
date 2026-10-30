"""Ingest documents (PDF + text) into per-user Weaviate tenants."""
import uuid
from collections.abc import Iterable
from pathlib import Path

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.collections import (
    add_documents_for,
    count_by_source_file,
    delete_by_source_file,
    delete_user_collection,
    docs_dir_for,
    ensure_tenant,
)

log = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}


def _load_one(path: Path) -> list[Document]:
    """Load a single file based on its extension."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return PyPDFLoader(str(path)).load()
    if ext in {".txt", ".md"}:
        return TextLoader(str(path), encoding="utf-8").load()
    if ext == ".docx":
        return Docx2txtLoader(str(path)).load()
    raise ValueError(f"Unsupported file type: {ext}")


def load_documents(docs_dir: Path) -> tuple[list[Document], int]:
    """Load every supported file under docs_dir. Returns (docs, file_count)."""
    files = sorted(
        p for p in docs_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not files:
        raise FileNotFoundError(
            f"No supported files in {docs_dir}. "
            f"Drop PDFs / TXT / MD / DOCX files there and try again."
        )

    docs: list[Document] = []
    for f in files:
        loaded = _load_one(f)
        for d in loaded:
            d.metadata["source_file"] = f.name
            d.metadata.setdefault("page", d.metadata.get("page", 0))
        docs.extend(loaded)
        log.info("loaded %s (%d sections)", f.name, len(loaded))
    return docs, len(files)


def chunk_documents(docs: Iterable[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(list(docs))


def ingest_for_user(user_id: str | uuid.UUID) -> dict:
    """Index every file in this user's docs folder into their tenant.

    Wipes the user's tenant first so re-runs produce a clean state. Use
    ingest_single_file_for_user() for incremental upload-then-index flows.
    """
    user_dir = docs_dir_for(user_id)
    log.info("ingesting for user %s from %s", user_id, user_dir)

    docs, n_files = load_documents(user_dir)
    log.info("loaded %d sections from %d files", len(docs), n_files)

    chunks = chunk_documents(docs)
    log.info("created %d chunks", len(chunks))

    # Wipe and recreate the tenant for a clean re-index.
    delete_user_collection(user_id)
    ensure_tenant(user_id)

    add_documents_for(user_id, chunks)
    log.info("ingestion complete for user %s", user_id)
    return {"files": n_files, "chunks": len(chunks)}


def ingest_single_file_for_user(
    user_id: str | uuid.UUID,
    file_path: Path,
) -> dict:
    """Index one file (typically just-uploaded) into the user's tenant.

    Does NOT wipe the existing tenant, but replaces any chunks already indexed
    for a file with the same name, so re-uploading does not create duplicates.
    The old chunks are removed only after the new file parsed and chunked
    successfully. Returns chunk counts for this file only.
    """
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {file_path.suffix}")

    log.info("ingesting single file %s for user %s", file_path.name, user_id)
    raw = _load_one(file_path)
    for d in raw:
        d.metadata["source_file"] = file_path.name
        d.metadata.setdefault("page", d.metadata.get("page", 0))
    chunks = chunk_documents(raw)

    replaced = delete_by_source_file(user_id, file_path.name)
    if replaced:
        log.info("replacing %d existing chunks of %s", replaced, file_path.name)

    # add_documents_for ensures the tenant exists, then adds (no wipe).
    add_documents_for(user_id, chunks)
    log.info("added %d chunks for %s", len(chunks), file_path.name)
    return {"file": file_path.name, "chunks": len(chunks), "replaced": replaced}


def delete_file_from_user(user_id: str | uuid.UUID, filename: str) -> int:
    """Remove all chunks for a specific source file from the user's tenant.

    Returns the number of chunks deleted.
    """
    return delete_by_source_file(user_id, filename)


def list_files_for_user(user_id: str | uuid.UUID) -> list[dict]:
    """List files in the user's docs folder with size + chunk-count metadata."""
    user_dir = docs_dir_for(user_id)
    files = []
    for path in sorted(user_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        files.append({
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "chunks_indexed": count_by_source_file(user_id, path.name),
        })
    return files


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m app.rag.ingestion <user_uuid>")
        sys.exit(1)
    result = ingest_for_user(sys.argv[1])
    print(f"\nIndexed {result['chunks']} chunks from {result['files']} files.")
