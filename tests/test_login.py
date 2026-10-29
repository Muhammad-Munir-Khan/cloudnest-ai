"""Login and suspension through the real /auth/jwt routes (fake user store)."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.auth import UserManager, get_user_manager

PASSWORD = "Correct-pass-1"


class _UserDB:
    def __init__(self, users):
        self.users = {u.email.lower(): u for u in users}

    async def get(self, user_id):
        return next((u for u in self.users.values() if u.id == user_id), None)

    async def get_by_email(self, email):
        return self.users.get(email.lower())

    async def update(self, user, update_dict):
        return user


@pytest.fixture
def setup(monkeypatch):
    from app.main import app

    monkeypatch.setattr(rate_limit, "_get_redis", lambda: None)
    monkeypatch.setattr(rate_limit, "_FAIL_OPEN", True)
    probe = UserManager(None)
    alice = SimpleNamespace(
        id=uuid.uuid4(), email="alice@example.com", hashed_password=probe.password_helper.hash(PASSWORD),
        is_active=True, is_superuser=False, is_verified=True, role="user",
        display_name=None, jwt_invalidated_at=None,
    )
    manager = UserManager(_UserDB([alice]))
    app.dependency_overrides[get_user_manager] = lambda: manager
    yield TestClient(app), alice
    app.dependency_overrides.clear()


def _login(client, email, password):
    return client.post("/auth/jwt/login", data={"username": email, "password": password})


def test_active_user_logs_in_and_reaches_protected_route(setup):
    client, alice = setup
    r = _login(client, alice.email, PASSWORD)
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == alice.email


def test_wrong_password_and_unknown_email_look_the_same(setup):
    client, alice = setup
    wrong = _login(client, alice.email, "nope")
    unknown = _login(client, "ghost@example.com", "nope")
    assert wrong.status_code == unknown.status_code == 400
    assert wrong.json() == unknown.json()


def test_suspended_user_with_correct_password_gets_403(setup):
    client, alice = setup
    alice.is_active = False
    r = _login(client, alice.email, PASSWORD)
    assert r.status_code == 403
    assert "access_token" not in r.json()


def test_suspended_user_with_wrong_password_is_not_revealed(setup):
    client, alice = setup
    alice.is_active = False
    assert _login(client, alice.email, "nope").json() == _login(client, "ghost@example.com", "nope").json()


def test_suspension_kills_an_existing_token(setup):
    client, alice = setup
    token = _login(client, alice.email, PASSWORD).json()["access_token"]
    alice.is_active = False
    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401
