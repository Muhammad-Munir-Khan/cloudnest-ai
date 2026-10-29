"""Weaviate client wiring: API-key auth is sent only when configured."""
import pytest

from app.core.config import settings
from app.rag import collections


@pytest.fixture
def captured(monkeypatch):
    calls = {}

    def fake_connect(**kwargs):
        calls.update(kwargs)
        return object()

    monkeypatch.setattr(collections.weaviate, "connect_to_custom", fake_connect)
    collections.get_weaviate_client.cache_clear()
    yield calls
    collections.get_weaviate_client.cache_clear()


def test_no_api_key_means_anonymous(captured, monkeypatch):
    monkeypatch.setattr(settings, "weaviate_api_key", None)
    collections.get_weaviate_client()
    assert captured["auth_credentials"] is None


def test_api_key_is_passed_to_client(captured, monkeypatch):
    monkeypatch.setattr(settings, "weaviate_api_key", "test-key")
    collections.get_weaviate_client()
    auth = captured["auth_credentials"]
    assert auth is not None
    assert getattr(auth, "api_key", None) == "test-key"
