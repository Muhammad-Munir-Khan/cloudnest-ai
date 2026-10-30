"""Tenant isolation against a real Weaviate (replaces app/rag/Isolation_test.py).

Skipped when Weaviate is not reachable. Start it with:
    docker compose -f docker/docker-compose.yml up -d weaviate

Isolation comes from the `tenant=` argument, not from the embeddings, so a
fake embedder is used (no 2 GB model download). Each run uses its own throwaway
collection so a developer's real index is never touched.
"""
import hashlib
import socket
import uuid
from urllib.parse import urlparse

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.rag import collections
from app.rag.collections import (
    add_documents_for,
    count_by_source_file,
    count_for,
    delete_by_source_file,
    delete_user_collection,
    fetch_all_for,
    search_for,
    tenant_for,
)

DIM = 64


class FakeEmbeddings(Embeddings):
    """Deterministic bag-of-words vectors: shared words give similar vectors."""

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * DIM
        for word in text.lower().split():
            h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
            v[h % DIM] += 1.0
        return v or [1.0] + [0.0] * (DIM - 1)

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def _weaviate_reachable() -> bool:
    parsed = urlparse(settings.weaviate_url)
    try:
        with socket.create_connection((parsed.hostname or "localhost", parsed.port or 8080), 2):
            return True
    except OSError:
        return False


@pytest.fixture
def weaviate_env(monkeypatch):
    if not _weaviate_reachable():
        pytest.skip(f"Weaviate not reachable at {settings.weaviate_url}")
    name = f"IsolationTest{uuid.uuid4().hex[:10]}"
    monkeypatch.setattr(settings, "weaviate_index_name", name)
    monkeypatch.setattr(collections, "get_embeddings", lambda: FakeEmbeddings())
    collections.get_store.cache_clear()
    collections.get_weaviate_client.cache_clear()
    try:
        yield name
    finally:
        try:
            collections.get_weaviate_client().collections.delete(name)
        finally:
            collections.get_store.cache_clear()
            collections.get_weaviate_client.cache_clear()


@pytest.fixture
def two_users(weaviate_env):
    alice, bob = uuid.uuid4(), uuid.uuid4()
    add_documents_for(alice, [
        Document(page_content="alice secret cat named mittens",
                 metadata={"source_file": "shared-name.txt", "page": 0}),
    ])
    add_documents_for(bob, [
        Document(page_content="bob secret spacecraft launches at dawn",
                 metadata={"source_file": "shared-name.txt", "page": 0}),
        Document(page_content="bob second spacecraft note",
                 metadata={"source_file": "bob-only.txt", "page": 0}),
    ])
    return alice, bob


def test_positive_control_each_user_finds_own_documents(two_users):
    alice, bob = two_users
    assert count_for(alice) == 1
    assert count_for(bob) == 2
    assert "mittens" in " ".join(d.page_content for d, _ in search_for(alice, "cat mittens", k=5))
    assert "spacecraft" in " ".join(d.page_content for d, _ in search_for(bob, "spacecraft", k=5))


def test_search_never_returns_another_users_documents(two_users):
    alice, bob = two_users
    alice_hits = " ".join(d.page_content for d, _ in search_for(alice, "spacecraft launches dawn", k=10))
    bob_hits = " ".join(d.page_content for d, _ in search_for(bob, "cat named mittens", k=10))
    assert "spacecraft" not in alice_hits.lower()
    assert "mittens" not in bob_hits.lower()


def test_fetch_all_is_scoped_to_the_tenant(two_users):
    alice, bob = two_users
    assert [d.page_content for d in fetch_all_for(alice)] == ["alice secret cat named mittens"]
    assert len(fetch_all_for(bob)) == 2


def test_delete_by_source_file_only_touches_own_tenant(two_users):
    alice, bob = two_users
    assert delete_by_source_file(alice, "shared-name.txt") == 1  # same filename as Bob's
    assert count_for(alice) == 0
    assert count_for(bob) == 2
    assert count_by_source_file(bob, "shared-name.txt") == 1


def test_deleting_a_tenant_leaves_others_intact(two_users):
    alice, bob = two_users
    delete_user_collection(alice)
    assert count_for(alice) == 0
    assert count_for(bob) == 2


def test_unknown_user_sees_nothing(weaviate_env, two_users):
    stranger = uuid.uuid4()
    assert search_for(stranger, "spacecraft cat", k=10) == []
    assert fetch_all_for(stranger) == []
    assert count_for(stranger) == 0


def test_store_refuses_queries_without_a_tenant(two_users):
    with pytest.raises(Exception):  # noqa: B017 - library raises when MT is on and tenant is missing
        collections.get_store().similarity_search("secret", k=5)


def test_tenant_names_are_distinct_per_user():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert tenant_for(a) != tenant_for(b)
    assert tenant_for(a) == tenant_for(str(a))
