"""Error responses must not leak exception text (SEC-08)."""
import json
import logging
import re
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import agent_routes, attachment_routes, rag_routes
from app.api.errors import internal_error
from app.core import rate_limit
from app.core.auth import current_active_user

SECRET = "password=hunter2 host=10.0.0.5 path=/app/data/docs/abc"
REF = re.compile(r"Reference: [0-9a-f]{12}$")


@pytest.fixture
def client(monkeypatch):
    from app.main import app

    monkeypatch.setattr(rate_limit, "_get_redis", lambda: None)
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False, is_active=True)
    app.dependency_overrides[current_active_user] = lambda: user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(current_active_user, None)


def _boom(*args, **kwargs):
    raise Exception(SECRET)


def test_internal_error_logs_detail_but_returns_generic(caplog):
    with caplog.at_level(logging.ERROR, logger="app.api.errors"):
        exc = internal_error("Ingestion failed", Exception(SECRET), "ingest file.pdf")
    assert exc.status_code == 500
    assert SECRET not in exc.detail and REF.search(exc.detail)
    ref = exc.detail.rsplit(" ", 1)[-1]
    assert any(ref in r.getMessage() and SECRET in r.getMessage() for r in caplog.records)


def test_rag_query_500_is_generic(client, monkeypatch):
    monkeypatch.setattr(rag_routes, "rag_answer", _boom)
    r = client.post("/rag/query", json={"question": "q"})
    assert r.status_code == 500
    assert SECRET not in r.text and REF.search(r.json()["detail"])


def test_reindex_404_hides_server_path(client, monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError("No supported files in /app/data/docs/abc")
    monkeypatch.setattr(rag_routes, "ingest_for_user", missing)
    r = client.post("/rag/reindex")
    assert r.status_code == 404
    assert "/app/data" not in r.text


def test_attachment_503_hides_provider_message(client, monkeypatch):
    def provider_down(*a, **k):
        raise RuntimeError("Groq vision call failed: upstream said " + SECRET)
    monkeypatch.setattr(attachment_routes, "extract_attachment", provider_down)
    r = client.post("/attachments/extract", files={"file": ("a.txt", b"hi", "text/plain")})
    assert r.status_code == 503
    assert SECRET not in r.text and REF.search(r.json()["detail"])


def test_stream_error_event_is_generic(client, monkeypatch):
    def failing_stream(*a, **k):
        raise Exception(SECRET)
        yield  # pragma: no cover - makes this a generator
    monkeypatch.setattr(agent_routes, "stream_agent", failing_stream)
    r = client.post("/agent/stream", json={"message": "hi", "session_id": "s1"})
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert events and events[-1]["type"] == "error"
    assert SECRET not in r.text and REF.search(events[-1]["message"])
