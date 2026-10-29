"""Per-request user context for the RAG layer.

LangChain tools (document_search, document_summarizer) are invoked by the
agent loop from inside graph.py — they don't receive the request's user_id
naturally. We pass it through a contextvar that the route sets and the tools
read.

This is the standard pattern for "ambient" request context in async Python.
contextvars are asyncio-aware (they propagate across awaits) and thread-safe
(each thread has its own value). The bg storage thread inherits the parent
context when we use run_coroutine_threadsafe.
"""
import contextvars
import uuid

# Default to the system user so background jobs (titler) and tests still work.
SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

_current_user_id: contextvars.ContextVar[uuid.UUID] = contextvars.ContextVar(
    "current_user_id",
    default=SYSTEM_USER_ID,
)


def set_current_user(user_id: str | uuid.UUID) -> contextvars.Token:
    """Set the current user for this context. Returns a token to reset with."""
    if isinstance(user_id, str):
        user_id = uuid.UUID(user_id)
    return _current_user_id.set(user_id)


def get_current_user() -> uuid.UUID:
    """Get the current user_id. Falls back to SYSTEM_USER_ID if unset."""
    return _current_user_id.get()


def reset_current_user(token: contextvars.Token) -> None:
    """Reset the user context using the token returned by set_current_user."""
    _current_user_id.reset(token)
