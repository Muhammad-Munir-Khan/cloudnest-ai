"""Bounded reading of uploaded files.

`data = await file.read()` followed by a length check loads the whole upload
into memory before rejecting it. read_upload_limited() reads in chunks and
aborts with 413 as soon as the limit is crossed.
"""
from fastapi import HTTPException, UploadFile

_CHUNK_BYTES = 1024 * 1024


async def read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Return the upload's bytes, or raise 413 once it exceeds max_bytes."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max {max_bytes // (1024 * 1024)} MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)
