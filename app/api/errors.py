"""Generic client-facing errors with a server-side reference.

Exception text can contain internal hostnames, SQL, file paths or provider
responses, so it is logged (with traceback) under a short reference id and
the client only sees a generic message plus that id. Support can then find
the full error in the logs.
"""
import uuid

from fastapi import HTTPException

from app.core.logging import get_logger

log = get_logger(__name__)


def error_reference() -> str:
    return uuid.uuid4().hex[:12]


def log_error(message: str, exc: BaseException, ref: str) -> None:
    log.error("%s (ref=%s): %s", message, ref, exc, exc_info=exc)


def internal_error(
    public_message: str,
    exc: BaseException,
    log_message: str | None = None,
    *,
    status_code: int = 500,
) -> HTTPException:
    """Log `exc` with a reference id and return a generic HTTPException.

    Usage: `raise internal_error("Ingestion failed", e, f"ingest {name}") from e`
    """
    ref = error_reference()
    log_error(log_message or public_message, exc, ref)
    return HTTPException(
        status_code=status_code, detail=f"{public_message}. Reference: {ref}"
    )
