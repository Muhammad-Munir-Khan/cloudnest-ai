"""Re-uploads replace old chunks (FN-02): admin corpus upload and exact-title delete."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import admin_routes
from app.core import rate_limit
from app.core.auth import current_active_user
from app.rag import global_collection


@pytest.fixture
def admin_client(monkeypatch):
    from app.main import app

    monkeypatch.setattr(rate_limit, "_get_redis", lambda: None)
    admin = SimpleNamespace(id=uuid.uuid4(), email="admin@example.com", role="corpus_admin",
                            is_active=True, is_superuser=False)
    app.dependency_overrides[current_active_user] = lambda: admin
    calls = []
    monkeypatch.setattr(admin_routes, "delete_by_source",
                        lambda title: calls.append(("delete", title)) or 3)
    monkeypatch.setattr(admin_routes, "add_to_global_corpus",
                        lambda items: calls.append(("add", len(items))) or len(items))
    monkeypatch.setattr(admin_routes, "global_corpus_count", lambda: 10)
    try:
        yield TestClient(app), calls
    finally:
        app.dependency_overrides.pop(current_active_user, None)


def test_upload_replaces_existing_source_before_adding(admin_client):
    client, calls = admin_client
    r = client.post("/admin/corpus/upload", params={"source_title": "Handbook"},
                    files={"file": ("handbook.txt", b"some text to index", "text/plain")})
    assert r.status_code == 200, r.text
    assert [c[0] for c in calls] == ["delete", "add"]
    assert calls[0] == ("delete", "Handbook")
    assert "Replaced 3 existing chunks of 'Handbook'" in r.json()["message"]


def test_source_title_defaults_to_the_file_name(admin_client):
    client, calls = admin_client
    client.post("/admin/corpus/upload",
                files={"file": ("policy.txt", b"text", "text/plain")})
    assert calls[0] == ("delete", "policy.txt")


def test_unparseable_file_leaves_the_existing_source_alone(admin_client):
    client, calls = admin_client
    r = client.post("/admin/corpus/upload",
                    files={"file": ("bad.txt", b"\xff\xfe\x00\xff", "text/plain")})
    assert r.status_code == 500
    assert calls == []  # nothing deleted, nothing added


class _Obj:
    def __init__(self, title):
        self.uuid = uuid.uuid4()
        self.properties = {"source_title": title}


class _FakeCollection:
    def __init__(self, titles):
        self.objs = [_Obj(t) for t in titles]
        self.deleted_ids = None
        self.query = SimpleNamespace(fetch_objects=self._fetch)
        self.data = SimpleNamespace(delete_many=self._delete)

    def _fetch(self, **kwargs):
        # Weaviate's word-tokenized equal filter also returns near matches.
        return SimpleNamespace(objects=self.objs)

    def _delete(self, where):
        self.deleted_ids = list(where.value)
        return SimpleNamespace(successful=len(self.deleted_ids), matches=len(self.deleted_ids))


def test_delete_by_source_only_deletes_the_exact_title(monkeypatch):
    coll = _FakeCollection(["Report", "Annual Report", "Report", "Report 2023"])
    client = SimpleNamespace(
        collections=SimpleNamespace(exists=lambda n: True, get=lambda n: coll))
    monkeypatch.setattr(global_collection, "get_weaviate_client", lambda: client)
    assert global_collection.delete_by_source("Report") == 2
    exact = {str(o.uuid) for o in coll.objs if o.properties["source_title"] == "Report"}
    assert {str(i) for i in coll.deleted_ids} == exact


def test_delete_by_source_without_exact_match_deletes_nothing(monkeypatch):
    coll = _FakeCollection(["Annual Report"])
    client = SimpleNamespace(
        collections=SimpleNamespace(exists=lambda n: True, get=lambda n: coll))
    monkeypatch.setattr(global_collection, "get_weaviate_client", lambda: client)
    assert global_collection.delete_by_source("Report") == 0
    assert coll.deleted_ids is None
