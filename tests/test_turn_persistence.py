"""RAG, ensemble and agent turns are saved with their sources (FN-01)."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent import graph, storage, turns
from app.agent.ensemble import EnsembleResponse
from app.api import agent_routes, rag_routes
from app.core import rate_limit
from app.core.auth import current_active_user
from app.core.schemas import QueryResponse, SourceInfo, ToolCall

SRC = SourceInfo(source_file="a.pdf", page=2, snippet="s", score=0.9, origin="personal")


@pytest.fixture
def saved(monkeypatch):
    """Record what reaches storage; stub out title generation."""
    rows: list[dict] = []

    def fake_append(session_id, role, content, metadata=None, user_id=None):
        rows.append({"session": session_id, "role": role, "content": content,
                     "meta": metadata, "user": user_id})
        return len(rows)

    titled: list[tuple] = []
    monkeypatch.setattr(storage, "append_message", fake_append)
    monkeypatch.setattr(turns, "maybe_generate_title", lambda *a: titled.append(a))
    monkeypatch.setattr(graph, "maybe_generate_title", lambda *a: titled.append(a))
    rows_titled = SimpleNamespace(rows=rows, titled=titled)
    return rows_titled


@pytest.fixture
def client(monkeypatch):
    from app.main import app

    monkeypatch.setattr(rate_limit, "_get_redis", lambda: None)
    user = SimpleNamespace(id=uuid.uuid4(), email="u@example.com", is_active=True,
                           is_superuser=False, role="user")
    app.dependency_overrides[current_active_user] = lambda: user
    try:
        yield TestClient(app), user
    finally:
        app.dependency_overrides.pop(current_active_user, None)


# ---- helpers -----------------------------------------------------------------

def test_turn_meta_is_json_ready_and_has_the_mode():
    meta = turns.turn_meta("agent", [SRC], [ToolCall(name="calculator", args={"expression": "1+1"},
                           result_preview="2")], 120)
    assert meta["mode"] == "agent" and meta["latency_ms"] == 120
    assert meta["sources"][0]["source_file"] == "a.pdf"
    assert meta["tool_calls"][0]["name"] == "calculator"
    import json
    json.dumps(meta)


def test_save_turn_without_a_session_stores_nothing(saved):
    turns.save_turn(None, uuid.uuid4(), "q", "a", {"mode": "rag"})
    assert saved.rows == [] and saved.titled == []


def test_save_turn_stores_question_then_answer_with_meta(saved):
    uid = uuid.uuid4()
    turns.save_turn("s1", uid, "q", "a", {"mode": "rag", "sources": []})
    assert [(r["role"], r["content"]) for r in saved.rows] == [("user", "q"), ("assistant", "a")]
    assert saved.rows[0]["meta"] is None and saved.rows[1]["meta"]["mode"] == "rag"
    assert len(saved.titled) == 1


def test_save_turn_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(storage, "append_message", boom)
    titled = []
    monkeypatch.setattr(turns, "maybe_generate_title", lambda *a: titled.append(a))
    turns.save_turn("s1", uuid.uuid4(), "q", "a", {"mode": "rag"})  # must not raise
    assert titled == []


# ---- RAG route ----------------------------------------------------------------

def test_rag_query_with_a_session_saves_the_turn_and_its_sources(client, saved, monkeypatch):
    tc, user = client
    resp = QueryResponse(answer="42", sources=[SRC], latency_ms=7)
    monkeypatch.setattr(rag_routes, "rag_answer", lambda *a, **k: resp)
    r = tc.post("/rag/query", json={"question": "what?", "session_id": "sid-1"})
    assert r.status_code == 200 and r.json()["answer"] == "42"
    assert [x["role"] for x in saved.rows] == ["user", "assistant"]
    assert saved.rows[0]["user"] == user.id and saved.rows[0]["session"] == "sid-1"
    meta = saved.rows[1]["meta"]
    assert meta["mode"] == "rag" and meta["sources"][0]["source_file"] == "a.pdf"
    assert meta["latency_ms"] == 7


def test_rag_query_without_a_session_saves_nothing(client, saved, monkeypatch):
    tc, _ = client
    monkeypatch.setattr(rag_routes, "rag_answer",
                        lambda *a, **k: QueryResponse(answer="x", sources=[], latency_ms=1))
    assert tc.post("/rag/query", json={"question": "what?"}).status_code == 200
    assert saved.rows == []


def test_rag_query_still_answers_when_saving_fails(client, monkeypatch):
    tc, _ = client
    monkeypatch.setattr(rag_routes, "rag_answer",
                        lambda *a, **k: QueryResponse(answer="x", sources=[], latency_ms=1))
    monkeypatch.setattr(storage, "append_message",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    r = tc.post("/rag/query", json={"question": "q", "session_id": "s"})
    assert r.status_code == 200 and r.json()["answer"] == "x"


# ---- ensemble route -------------------------------------------------------------

def test_ensemble_saves_question_and_verdict_only(client, saved, monkeypatch):
    tc, _ = client

    async def fake_ensemble(message, language="en"):
        return EnsembleResponse(
            question=message,
            candidates=[{"model": "a", "answer": "long candidate answer", "latency_ms": 5, "error": None}],
            ranking=[], verdict="the verdict", judge_model="judge-1", total_latency_ms=99)

    monkeypatch.setattr(agent_routes, "run_ensemble_async", fake_ensemble)
    r = tc.post("/agent/ensemble", json={"message": "which?", "session_id": "sid-2"})
    assert r.status_code == 200
    assert [(x["role"], x["content"]) for x in saved.rows] == [("user", "which?"), ("assistant", "the verdict")]
    meta = saved.rows[1]["meta"]
    assert meta["mode"] == "ensemble" and meta["judge_model"] == "judge-1" and meta["latency_ms"] == 99
    assert "long candidate answer" not in str(saved.rows)


# ---- agent ---------------------------------------------------------------------

def test_agent_turn_stores_sources_and_tool_calls(saved, monkeypatch):
    final = [
        HumanMessage(content="find it"),
        AIMessage(content="", tool_calls=[{"name": "document_search", "args": {"question": "find it"}, "id": "c1"}]),
        ToolMessage(content="the text", tool_call_id="c1", name="document_search",
                    artifact=[SRC.model_dump()]),
        AIMessage(content="found it"),
    ]
    monkeypatch.setattr(graph, "get_graph", lambda: SimpleNamespace(invoke=lambda *a, **k: {"messages": final}))
    monkeypatch.setattr(graph.memory, "get", lambda *a, **k: [])
    uid = uuid.uuid4()
    resp = graph.run_agent("find it", "sid-3", user_id=uid)
    assert resp.sources[0].source_file == "a.pdf"
    user_row, assistant_row = saved.rows
    assert (user_row["role"], user_row["meta"]) == ("user", None)
    meta = assistant_row["meta"]
    assert meta["mode"] == "agent"
    assert meta["sources"][0]["source_file"] == "a.pdf"
    assert meta["tool_calls"][0]["name"] == "document_search"
    assert meta["latency_ms"] == resp.latency_ms
