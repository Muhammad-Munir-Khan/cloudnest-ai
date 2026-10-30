"""Shared fixtures for tests that need a real Weaviate (skipped when it is down).

Start one with: docker compose -f docker/docker-compose.yml up -d weaviate
(set WEAVIATE_URL=http://localhost:8080 if .env uses the Docker hostname).
Isolation and re-upload behaviour depend on the `tenant=` argument and source
file names, not on embedding quality, so a fake embedder avoids the 2 GB model.
"""
import hashlib
import socket
import uuid
from urllib.parse import urlparse

import pytest
from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.rag import collections

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
