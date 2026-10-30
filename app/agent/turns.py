"""Saving chat turns that do not go through the agent graph (RAG, ensemble).

Agent turns are saved by `run_agent` / `stream_agent`. RAG-only and ensemble
requests are single calls, so the routes use `save_turn` to store the question
and the answer in the same chat history, with the same metadata shape, so a
reloaded session shows them again.
"""
import uuid
from collections.abc import Iterable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.memory import memory
from app.agent.titler import maybe_generate_title
from app.core.logging import get_logger

log = get_logger(__name__)


def turn_meta(
    mode: str,
    sources: Iterable[Any] = (),
    tool_calls: Iterable[Any] = (),
    latency_ms: int | None = None,
    **extra: Any,
) -> dict:
    """Metadata stored with an assistant message (JSON-serialisable).

    `mode` is "agent", "rag" or "ensemble". `sources` and `tool_calls` are
    pydantic models (SourceInfo, ToolCall). Never fed back to the model.
    """
    meta: dict[str, Any] = {
        "mode": mode,
        "sources": [s.model_dump() for s in sources],
        "tool_calls": [tc.model_dump() for tc in tool_calls],
    }
    if latency_ms is not None:
        meta["latency_ms"] = latency_ms
    meta.update(extra)
    return meta


def save_turn(
    session_id: str | None,
    user_id: str | uuid.UUID,
    question: str,
    answer: str,
    meta: dict,
) -> None:
    """Store one question/answer pair in the session; never raises.

    Does nothing without a session id (older clients). A storage failure is
    logged and swallowed so the user still gets the answer they asked for.
    """
    if not session_id:
        return
    try:
        memory.append(session_id, HumanMessage(content=question), user_id=user_id)
        memory.append(session_id, AIMessage(content=answer), user_id=user_id, meta=meta)
    except Exception as e:
        log.warning("could not save %s turn for session %s: %s", meta.get("mode"), session_id, e)
        return
    maybe_generate_title(session_id, user_id, question, answer)
