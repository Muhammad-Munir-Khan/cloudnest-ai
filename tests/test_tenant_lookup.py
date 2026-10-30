"""Tenant checks must not list every user's tenant (cost grew with the user count)."""
import uuid
from types import SimpleNamespace

import pytest

from app.rag import collections


class FakeTenants:
    def __init__(self, existing=()):
        self.existing = set(existing)
        self.created: list[str] = []
        self.removed: list[str] = []

    def get(self):
        raise AssertionError("tenants.get() lists every user's tenant")

    def exists(self, name):
        return name in self.existing

    def create(self, tenants):
        for t in tenants:
            self.existing.add(t.name)
            self.created.append(t.name)

    def remove(self, names):
        for n in names:
            self.existing.discard(n)
            self.removed.append(n)


@pytest.fixture
def tenants(monkeypatch):
    t = FakeTenants()
    coll = SimpleNamespace(tenants=t)
    client = SimpleNamespace(collections=SimpleNamespace(
        exists=lambda name: True, get=lambda name: coll))
    monkeypatch.setattr(collections, "get_weaviate_client", lambda: client)
    return t


def test_tenant_exists_uses_a_direct_lookup(tenants):
    user = uuid.uuid4()
    assert collections._tenant_exists(user) is False
    tenants.existing.add(collections.tenant_for(user))
    assert collections._tenant_exists(user) is True


def test_ensure_tenant_creates_only_when_missing(tenants):
    user = uuid.uuid4()
    collections.ensure_tenant(user)
    collections.ensure_tenant(user)
    assert tenants.created == [collections.tenant_for(user)]


def test_delete_user_collection_removes_only_an_existing_tenant(tenants):
    user = uuid.uuid4()
    collections.delete_user_collection(user)  # nothing to remove
    tenants.existing.add(collections.tenant_for(user))
    collections.delete_user_collection(user)
    assert tenants.removed == [collections.tenant_for(user)]
