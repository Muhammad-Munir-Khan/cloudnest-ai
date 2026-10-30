"""alist_sessions against a real Postgres: right counts, only the caller's sessions.

Runs only when TEST_DATABASE_URL points at a throwaway database, e.g.
    docker run -d --rm -p 55432:5432 -e POSTGRES_PASSWORD=x -e POSTGRES_DB=t postgres:16-alpine
    TEST_DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:55432/t pytest tests/integration
It creates and drops all tables, so never point it at a real database.
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401  (registers every model on Base)
from app.agent import storage
from app.core.db import Base
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


async def _seed(maker):
    """Three users; sessions with 0..n messages; returns {user_id: {session_id: n}}."""
    now = datetime.now(timezone.utc)
    expected: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
    async with maker() as db:
        for u in range(3):
            user = User(id=uuid.uuid4(), email=f"u{u}@example.com", hashed_password="x",
                        is_active=True, is_superuser=False, is_verified=True)
            db.add(user)
            await db.flush()
            expected[user.id] = {}
            for s in range(4):
                sid = uuid.uuid4()
                db.add(ChatSession(id=sid, user_id=user.id, title=f"chat {u}-{s}",
                                   updated_at=now - timedelta(minutes=s)))
                await db.flush()
                n = (u + 1) * s  # includes sessions with no messages (s == 0)
                for k in range(n):
                    db.add(ChatMessage(session_id=sid, role="user", content=f"m{k}"))
                expected[user.id][sid] = n
        await db.commit()
    return expected


def test_alist_sessions_counts_only_the_callers_sessions(monkeypatch):
    async def go():
        engine = create_async_engine(URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(storage, "get_or_create_bg_engine", lambda: maker)
        try:
            expected = await _seed(maker)
            for user_id, sessions in expected.items():
                rows = await storage.alist_sessions(user_id)
                got = {uuid.UUID(r["id"]): r["message_count"] for r in rows}
                assert got == sessions
                # newest first
                updated = [r["updated_at"] for r in rows]
                assert updated == sorted(updated, reverse=True)
            limited = await storage.alist_sessions(next(iter(expected)), limit=2)
            assert len(limited) == 2
            assert await storage.alist_sessions(uuid.uuid4()) == []
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    asyncio.run(go())
