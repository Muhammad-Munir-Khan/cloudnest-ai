"""Force-logout (JWT freshness) enforcement and token revocation tests."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.core.auth import UserManager, _check_freshness, current_active_user
from app.core.config import settings

# Routes that are intentionally reachable without the freshness check:
# login/register/reset/verify/OAuth/logout and public probes.
PUBLIC_PREFIXES = ("/auth/", "/health", "/docs", "/redoc", "/openapi.json")
PUBLIC_EXACT = {"/"}


def _dependency_calls(dependant) -> set:
    calls = set()
    for dep in dependant.dependencies:
        calls.add(dep.call)
        calls |= _dependency_calls(dep)
    return calls


def test_every_authenticated_route_runs_freshness_check():
    from app.main import app

    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in PUBLIC_EXACT or route.path.startswith(PUBLIC_PREFIXES):
            continue
        if current_active_user not in _dependency_calls(route.dependant):
            missing.append(f"{sorted(route.methods)} {route.path}")
    assert not missing, f"routes without freshness check: {missing}"


def test_users_routes_are_covered():
    from app.main import app

    users_routes = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/users")]
    assert users_routes  # sanity: router is mounted
    for r in users_routes:
        assert current_active_user in _dependency_calls(r.dependant), r.path


def _token(iat: datetime) -> str:
    payload = {
        "sub": str(uuid.uuid4()),
        "aud": "fastapi-users:auth",
        "iat": int(iat.timestamp()),
        "exp": int((iat + timedelta(hours=1)).timestamp()),
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _request(token: str):
    return SimpleNamespace(headers={"Authorization": f"Bearer {token}"}, cookies={})


def test_token_issued_before_cutoff_is_rejected():
    now = datetime.now(timezone.utc)
    user = SimpleNamespace(jwt_invalidated_at=now)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_check_freshness(_request(_token(now - timedelta(minutes=5))), user))
    assert exc.value.status_code == 401


def test_token_issued_after_cutoff_is_accepted():
    now = datetime.now(timezone.utc)
    user = SimpleNamespace(jwt_invalidated_at=now - timedelta(minutes=5))
    assert asyncio.run(_check_freshness(_request(_token(now)), user)) is user


class _FakeUserDB:
    def __init__(self):
        self.updates: list[dict] = []

    async def update(self, user, update_dict):
        self.updates.append(update_dict)
        return user


def _user():
    return SimpleNamespace(id=uuid.uuid4(), email="u@example.com", role="user", is_superuser=False)


def test_password_change_revokes_existing_tokens():
    db = _FakeUserDB()
    asyncio.run(UserManager(db).on_after_update(_user(), {"password": "new-secret"}))
    assert any("jwt_invalidated_at" in u for u in db.updates)


def test_non_password_update_keeps_tokens():
    db = _FakeUserDB()
    asyncio.run(UserManager(db).on_after_update(_user(), {"display_name": "New"}))
    assert not any("jwt_invalidated_at" in u for u in db.updates)


def test_password_reset_revokes_existing_tokens(monkeypatch):
    sent = []

    async def fake_send(*args, **kwargs):
        sent.append(args)

    monkeypatch.setattr("app.core.auth.send_email", fake_send)
    db = _FakeUserDB()
    asyncio.run(UserManager(db).on_after_reset_password(_user()))
    assert any("jwt_invalidated_at" in u for u in db.updates)
    assert sent  # "password changed" notice still sent
