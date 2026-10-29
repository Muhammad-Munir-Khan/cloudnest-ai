"""Admin RBAC and super-admin self-protection (app/api/admin_routes.py)."""
import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.admin_deps import require_corpus_admin, require_super_admin
from app.core.auth import current_active_user
from app.core.db import get_async_session

SUPER_ONLY_PREFIXES = ("/admin/users", "/admin/stats")


def _user(role="user", **kw):
    fields = dict(
        id=uuid.uuid4(), email=f"{role}-{uuid.uuid4().hex[:6]}@example.com", role=role,
        is_active=True, is_verified=True, display_name=None, created_at=None,
    )
    fields.update(kw)
    return SimpleNamespace(**fields)


class FakeSession:
    """Returns `target` for every SELECT; records statements and commits."""

    def __init__(self, target):
        self.target = target
        self.statements = []
        self.committed = False

    async def execute(self, stmt):
        self.statements.append(stmt)
        one = SimpleNamespace(one_or_none=lambda: self.target)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(unique=lambda: one))

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


def _dependency_calls(dependant) -> set:
    calls = set()
    for dep in dependant.dependencies:
        calls.add(dep.call)
        calls |= _dependency_calls(dep)
    return calls


@pytest.fixture
def app(monkeypatch):
    from app.main import app

    monkeypatch.setattr(rate_limit, "_get_redis", lambda: None)
    monkeypatch.setattr(rate_limit, "_FAIL_OPEN", True)
    yield app
    app.dependency_overrides.clear()


def _client(app, actor, session=None):
    app.dependency_overrides[current_active_user] = lambda: actor
    if session is not None:
        app.dependency_overrides[get_async_session] = lambda: session
    return TestClient(app)


def _admin_routes():
    from app.main import app

    return [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/admin")]


def test_every_admin_route_requires_a_role():
    routes = _admin_routes()
    assert routes
    for r in routes:
        calls = _dependency_calls(r.dependant)
        assert calls & {require_corpus_admin, require_super_admin}, r.path


def test_user_management_requires_super_admin():
    for r in _admin_routes():
        if r.path.startswith(SUPER_ONLY_PREFIXES):
            assert require_super_admin in _dependency_calls(r.dependant), r.path


@pytest.mark.parametrize(
    ("role", "path"),
    [
        ("user", "/admin/users"),
        ("user", "/admin/corpus/stats"),
        ("corpus_admin", "/admin/users"),
        ("corpus_admin", "/admin/stats"),
    ],
)
def test_insufficient_role_is_forbidden(app, role, path):
    r = _client(app, _user(role)).get(path)
    assert r.status_code == 403


@pytest.mark.parametrize(
    ("checker", "role", "ok"),
    [
        (require_corpus_admin, "user", False),
        (require_corpus_admin, "corpus_admin", True),
        (require_corpus_admin, "super_admin", True),
        (require_super_admin, "corpus_admin", False),
        (require_super_admin, "super_admin", True),
    ],
)
def test_role_hierarchy(checker, role, ok):
    actor = _user(role)
    if ok:
        assert asyncio.run(checker(user=actor)) is actor
    else:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(checker(user=actor))
        assert exc.value.status_code == 403


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("patch", "/role", {"role": "user"}),
        ("patch", "/active", {"is_active": False}),
        ("post", "/force-logout", None),
        ("delete", "", None),
    ],
)
def test_super_admin_cannot_lock_themselves_out(app, method, suffix, body):
    admin = _user("super_admin")
    session = FakeSession(admin)
    client = _client(app, admin, session)
    kwargs = {"json": body} if body is not None else {}
    r = getattr(client, method)(f"/admin/users/{admin.id}{suffix}", **kwargs)
    assert r.status_code == 400
    assert not session.committed


def test_block_deactivates_and_revokes_sessions_in_one_update(app, monkeypatch):
    from app.api import admin_routes

    async def no_email(*args, **kwargs):
        return None

    monkeypatch.setattr(admin_routes, "send_email", no_email)
    admin, target = _user("super_admin"), _user("user")
    session = FakeSession(target)
    r = _client(app, admin, session).patch(
        f"/admin/users/{target.id}/active", json={"is_active": False, "reason": "spam"}
    )
    assert r.status_code == 200
    assert session.committed
    params = session.statements[-1].compile().params
    assert params["is_active"] is False
    assert params["jwt_invalidated_at"] is not None
