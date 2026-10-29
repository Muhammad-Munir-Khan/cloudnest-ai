"""Conversation memory (app.agent.memory.Memory) with storage stubbed out.

Memory is a thin adapter over app.agent.storage (Postgres). These tests
replace the storage calls so they run without a database.
"""
import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent import memory as memory_module
from app.agent import storage
from app.core.config import settings


@pytest.fixture
def fake_storage(monkeypatch):
    rows: list[dict] = []
    calls: dict = {}

    async def fake_recent(user_id, session_id, limit):
        calls["recent"] = (user_id, session_id, limit)
        return rows[-limit:]

    def fake_append(session_id, role, content, metadata=None, user_id=storage.SYSTEM_USER_ID):
        rows.append({"role": role, "content": content})
        return len(rows)

    def fake_delete(session_id, user_id=storage.SYSTEM_USER_ID):
        calls["delete"] = (session_id, user_id)
        rows.clear()
        return True

    monkeypatch.setattr(storage, "alist_recent_messages", fake_recent)
    monkeypatch.setattr(storage, "_run_sync", asyncio.run)
    monkeypatch.setattr(storage, "append_message", fake_append)
    monkeypatch.setattr(storage, "delete_session", fake_delete)
    return rows, calls


def test_append_maps_roles(fake_storage):
    rows, _ = fake_storage
    m = memory_module.Memory()
    m.append("s1", HumanMessage(content="hi"), user_id="u1")
    m.append("s1", AIMessage(content="hello"), user_id="u1")
    m.append("s1", SystemMessage(content="note"), user_id="u1")
    assert [r["role"] for r in rows] == ["user", "assistant", "system"]


def test_get_returns_langchain_messages_in_order(fake_storage):
    rows, _ = fake_storage
    rows += [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    msgs = memory_module.Memory().get("s1", user_id="u1")
    assert isinstance(msgs[0], HumanMessage) and msgs[0].content == "q"
    assert isinstance(msgs[1], AIMessage) and msgs[1].content == "a"


def test_get_uses_window_of_two_messages_per_pair(fake_storage, monkeypatch):
    rows, calls = fake_storage
    monkeypatch.setattr(settings, "memory_window", 2)
    rows += [{"role": "user", "content": str(i)} for i in range(10)]
    msgs = memory_module.Memory().get("s1", user_id="u1")
    assert calls["recent"] == ("u1", "s1", 4)
    assert [m.content for m in msgs] == ["6", "7", "8", "9"]


def test_get_scopes_by_user(fake_storage):
    _, calls = fake_storage
    memory_module.Memory().get("s1", user_id="owner-uuid")
    assert calls["recent"][0] == "owner-uuid"


def test_system_rows_are_replayed_as_human(fake_storage):
    rows, _ = fake_storage
    rows.append({"role": "system", "content": "legacy"})
    msgs = memory_module.Memory().get("s1", user_id="u1")
    assert isinstance(msgs[0], HumanMessage)


def test_clear_deletes_session(fake_storage):
    rows, calls = fake_storage
    rows.append({"role": "user", "content": "x"})
    memory_module.Memory().clear("s1", user_id="u1")
    assert calls["delete"] == ("s1", "u1") and rows == []
