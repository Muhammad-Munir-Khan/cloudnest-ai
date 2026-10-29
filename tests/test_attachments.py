"""Attachment extraction must not keep raw uploads on disk (SEC-09, SEC-14)."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.auth import current_active_user
from app.core.config import settings
from app.rag.collections import delete_user_workspace_dir


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.main import app

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(rate_limit, "_get_redis", lambda: None)  # limiter no-op
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=True, is_active=True)
    app.dependency_overrides[current_active_user] = lambda: user
    try:
        yield TestClient(app), tmp_path
    finally:
        app.dependency_overrides.pop(current_active_user, None)


def test_extract_returns_text_without_writing_files(client):
    tc, data_dir = client
    r = tc.post(
        "/attachments/extract",
        files={"file": ("notes.txt", b"hello attachment", "text/plain")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hello attachment"
    assert list(data_dir.rglob("*")) == []  # nothing persisted, no repl_workspace


def test_legacy_persist_flag_no_longer_writes_or_indexes(client, monkeypatch):
    """Even a superuser's persist=true used to copy into data/docs and re-index
    every user's folder into one tenant; the flag is now ignored."""
    tc, data_dir = client
    r = tc.post(
        "/attachments/extract",
        files={"file": ("notes.txt", b"private", "text/plain")},
        data={"persist": "true"},
    )
    assert r.status_code == 200, r.text
    assert list(data_dir.rglob("*")) == []


def test_no_global_ingest_entry_points():
    from fastapi.routing import APIRoute

    from app.main import app
    from app.rag import ingestion

    paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
    assert "/rag/ingest" not in paths
    assert not hasattr(ingestion, "ingest")


def test_delete_user_workspace_dir_removes_legacy_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    uid = uuid.uuid4()
    legacy = tmp_path / "repl_workspace" / uid.hex
    legacy.mkdir(parents=True)
    (legacy / "old-upload.pdf").write_bytes(b"%PDF-")
    delete_user_workspace_dir(uid)
    assert not legacy.exists()


def test_delete_user_workspace_dir_is_noop_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    delete_user_workspace_dir(str(uuid.uuid4()))  # must not raise
