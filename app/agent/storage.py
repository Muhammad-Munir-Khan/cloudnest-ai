"""Postgres-backed chat session and message storage.

All async DB operations run on a dedicated background event loop with their
OWN engine/pool (created via get_or_create_bg_engine). This keeps asyncpg
connections bound to the bg loop so they never collide with FastAPI's main
loop where auth and async routes live.
"""
import asyncio
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func, select, update

from app.core.db import get_or_create_bg_engine
from app.core.logging import get_logger
from app.models.chat import ChatMessage, ChatSession

log = get_logger(__name__)

SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    s = str(value)
    try:
        return uuid.UUID(s)
    except ValueError:
        return uuid.uuid5(_NAMESPACE, s)


# =============================================================================
# Async core (runs on the background event loop)
# =============================================================================

async def acreate_session(
    user_id: str | uuid.UUID,
    session_id: str | uuid.UUID | None = None,
    title: str = "New chat",
) -> dict[str, Any]:
    user_uuid = _coerce_uuid(user_id)
    session_uuid = _coerce_uuid(session_id) if session_id else uuid.uuid4()
    maker = get_or_create_bg_engine()

    async with maker() as db:
        chat = ChatSession(
            id=session_uuid,
            user_id=user_uuid,
            title=title,
            title_locked=False,
        )
        db.add(chat)
        await db.commit()
        await db.refresh(chat)
        return _session_to_dict(chat, message_count=0)


async def aget_session(
    user_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
) -> dict[str, Any] | None:
    user_uuid = _coerce_uuid(user_id)
    session_uuid = _coerce_uuid(session_id)
    maker = get_or_create_bg_engine()

    async with maker() as db:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_uuid,
                ChatSession.user_id == user_uuid,
            )
        )
        chat = result.scalar_one_or_none()
        if not chat:
            return None
        count = await _count_messages(db, session_uuid)
        return _session_to_dict(chat, message_count=count)


async def alist_sessions(
    user_id: str | uuid.UUID,
    limit: int = 200,
) -> list[dict[str, Any]]:
    user_uuid = _coerce_uuid(user_id)
    maker = get_or_create_bg_engine()

    async with maker() as db:
        msg_counts = (
            select(
                ChatMessage.session_id,
                func.count(ChatMessage.id).label("count"),
            )
            .group_by(ChatMessage.session_id)
            .subquery()
        )
        result = await db.execute(
            select(ChatSession, msg_counts.c.count)
            .outerjoin(msg_counts, ChatSession.id == msg_counts.c.session_id)
            .where(ChatSession.user_id == user_uuid)
            .order_by(desc(ChatSession.updated_at))
            .limit(limit)
        )
        rows = result.all()
        return [
            _session_to_dict(chat, message_count=count or 0)
            for chat, count in rows
        ]


async def arename_session(
    user_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
    title: str,
    *,
    lock: bool = True,
) -> bool:
    user_uuid = _coerce_uuid(user_id)
    session_uuid = _coerce_uuid(session_id)
    maker = get_or_create_bg_engine()

    async with maker() as db:
        result = await db.execute(
            update(ChatSession)
            .where(
                ChatSession.id == session_uuid,
                ChatSession.user_id == user_uuid,
            )
            .values(title=title, title_locked=lock, updated_at=_utcnow())
        )
        await db.commit()
        return result.rowcount > 0


async def aauto_set_title(
    user_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
    title: str,
) -> bool:
    user_uuid = _coerce_uuid(user_id)
    session_uuid = _coerce_uuid(session_id)
    maker = get_or_create_bg_engine()

    async with maker() as db:
        result = await db.execute(
            update(ChatSession)
            .where(
                ChatSession.id == session_uuid,
                ChatSession.user_id == user_uuid,
                ChatSession.title_locked == False,  # noqa: E712
            )
            .values(title=title, updated_at=_utcnow())
        )
        await db.commit()
        return result.rowcount > 0


async def adelete_session(
    user_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
) -> bool:
    user_uuid = _coerce_uuid(user_id)
    session_uuid = _coerce_uuid(session_id)
    maker = get_or_create_bg_engine()

    async with maker() as db:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_uuid,
                ChatSession.user_id == user_uuid,
            )
        )
        chat = result.scalar_one_or_none()
        if not chat:
            return False
        await db.delete(chat)
        await db.commit()
        return True


async def aappend_message(
    user_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
    role: str,
    content: str,
    meta: dict | None = None,
) -> int:
    user_uuid = _coerce_uuid(user_id)
    session_uuid = _coerce_uuid(session_id)
    maker = get_or_create_bg_engine()

    async with maker() as db:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_uuid,
                ChatSession.user_id == user_uuid,
            )
        )
        chat = result.scalar_one_or_none()
        if not chat:
            chat = ChatSession(
                id=session_uuid,
                user_id=user_uuid,
                title="New chat",
                title_locked=False,
            )
            db.add(chat)
            await db.flush()
        else:
            chat.updated_at = _utcnow()

        msg = ChatMessage(
            session_id=session_uuid,
            role=role,
            content=content,
            meta=meta,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        return msg.id


async def alist_messages(
    user_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    user_uuid = _coerce_uuid(user_id)
    session_uuid = _coerce_uuid(session_id)
    maker = get_or_create_bg_engine()

    async with maker() as db:
        sess_check = await db.execute(
            select(ChatSession.id).where(
                ChatSession.id == session_uuid,
                ChatSession.user_id == user_uuid,
            )
        )
        if not sess_check.scalar_one_or_none():
            return []

        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_uuid)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        if limit:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        msgs = result.scalars().all()
        return [_message_to_dict(m) for m in msgs]


async def alist_recent_messages(
    user_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
    limit: int,
) -> list[dict[str, Any]]:
    user_uuid = _coerce_uuid(user_id)
    session_uuid = _coerce_uuid(session_id)
    maker = get_or_create_bg_engine()

    async with maker() as db:
        sess_check = await db.execute(
            select(ChatSession.id).where(
                ChatSession.id == session_uuid,
                ChatSession.user_id == user_uuid,
            )
        )
        if not sess_check.scalar_one_or_none():
            return []

        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_uuid)
            .order_by(desc(ChatMessage.created_at), desc(ChatMessage.id))
            .limit(limit)
        )
        msgs = list(result.scalars().all())
        msgs.reverse()
        return [_message_to_dict(m) for m in msgs]


# =============================================================================
# Persistent background event loop for sync→async bridging
# =============================================================================

_bg_loop: asyncio.AbstractEventLoop | None = None
_bg_thread: threading.Thread | None = None
_bg_loop_lock = threading.Lock()


def _ensure_bg_loop() -> asyncio.AbstractEventLoop:
    global _bg_loop, _bg_thread
    with _bg_loop_lock:
        if _bg_loop is not None and _bg_loop.is_running():
            return _bg_loop

        new_loop = asyncio.new_event_loop()

        def _run():
            asyncio.set_event_loop(new_loop)
            new_loop.run_forever()

        thread = threading.Thread(
            target=_run,
            daemon=True,
            name="storage-bg-loop",
        )
        thread.start()

        _bg_loop = new_loop
        _bg_thread = thread
        log.debug("started background storage event loop in thread %s", thread.name)
        return _bg_loop


def _run_sync(coro):
    """Run an async coroutine on the persistent background loop, block for result."""
    loop = _ensure_bg_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


# =============================================================================
# Sync wrappers (legacy non-async call sites)
# =============================================================================

def create_session(
    session_id: str | None = None,
    user_id: str | uuid.UUID = SYSTEM_USER_ID,
) -> dict[str, Any]:
    return _run_sync(acreate_session(user_id, session_id))


def get_session(
    session_id: str,
    user_id: str | uuid.UUID = SYSTEM_USER_ID,
) -> dict[str, Any] | None:
    return _run_sync(aget_session(user_id, session_id))


def list_sessions(
    limit: int = 200,
    user_id: str | uuid.UUID = SYSTEM_USER_ID,
) -> list[dict[str, Any]]:
    return _run_sync(alist_sessions(user_id, limit))


def rename_session(
    session_id: str,
    title: str,
    user_id: str | uuid.UUID = SYSTEM_USER_ID,
) -> bool:
    return _run_sync(arename_session(user_id, session_id, title, lock=True))


def auto_set_title(
    session_id: str,
    title: str,
    user_id: str | uuid.UUID = SYSTEM_USER_ID,
) -> bool:
    return _run_sync(aauto_set_title(user_id, session_id, title))


def delete_session(
    session_id: str,
    user_id: str | uuid.UUID = SYSTEM_USER_ID,
) -> bool:
    return _run_sync(adelete_session(user_id, session_id))


def append_message(
    session_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
    user_id: str | uuid.UUID = SYSTEM_USER_ID,
) -> int:
    return _run_sync(aappend_message(user_id, session_id, role, content, metadata))


def list_messages(
    session_id: str,
    limit: int | None = None,
    user_id: str | uuid.UUID = SYSTEM_USER_ID,
) -> list[dict[str, Any]]:
    return _run_sync(alist_messages(user_id, session_id, limit))


# =============================================================================
# Helpers
# =============================================================================

async def _count_messages(db, session_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
    )
    return result.scalar() or 0


def _session_to_dict(chat: ChatSession, message_count: int) -> dict[str, Any]:
    return {
        "id": str(chat.id),
        "title": chat.title,
        "created_at": chat.created_at.timestamp(),
        "updated_at": chat.updated_at.timestamp(),
        "message_count": message_count,
    }


def _message_to_dict(msg: ChatMessage) -> dict[str, Any]:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "created_at": msg.created_at.timestamp(),
        "metadata": msg.meta,
    }
