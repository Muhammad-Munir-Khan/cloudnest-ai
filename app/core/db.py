"""Async SQLAlchemy engine and session factory.

Two engines, two pools — one bound to FastAPI's main event loop (used by
async routes and the auth dependency), one bound to our background storage
loop (used by sync code via _run_sync).

Why two engines? asyncpg connections cannot be shared across event loops.
SQLAlchemy's pool keeps connections alive between requests; if those
connections were created on loop A and you try to use them from loop B,
you get the dreaded 'attached to a different loop' RuntimeError. By giving
each loop its own pool, no connection ever crosses loops.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Common engine kwargs — same connection settings for both engines.
_engine_kwargs = dict(
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)

# Engine A — used by FastAPI's main event loop (async routes, auth dependency).
# Created at module import; FastAPI's loop will adopt it on first use.
engine = create_async_engine(settings.database_url, **_engine_kwargs)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Engine B — used exclusively from app/agent/storage.py's background loop.
# Created lazily inside that module to ensure it binds to the bg loop, not main.
bg_engine = None
bg_session_maker = None


def get_or_create_bg_engine():
    """Create the background engine if not yet present.

    Called from inside the storage background loop so that asyncpg's connection
    setup runs on that loop, binding the pool's connections to it.
    """
    global bg_engine, bg_session_maker
    if bg_engine is None:
        bg_engine = create_async_engine(settings.database_url, **_engine_kwargs)
        bg_session_maker = async_sessionmaker(
            bg_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return bg_session_maker


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a session from the MAIN-loop engine.

    This is the session that fastapi-users uses for auth queries. Storage code
    in app/agent/storage.py uses bg_session_maker via get_or_create_bg_engine().
    """
    async with async_session_maker() as session:
        yield session
