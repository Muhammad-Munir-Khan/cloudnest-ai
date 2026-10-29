"""Per-account login lockout and per-address email quotas (SEC-17)."""
import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import auth, rate_limit
from app.core.auth import (
    EMAILS_PER_ADDRESS_LIMIT,
    LOGIN_FAILURE_LIMIT,
    UserManager,
)

PASSWORD = "Correct-pass-1"


class FakeRedis:
    def __init__(self):
        self.store: dict[str, int] = {}

    async def get(self, key):
        return self.store.get(key)

    async def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key, seconds):
        return True


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "_get_redis", lambda: fake)
    return fake


class _UserDB:
    def __init__(self, users):
        self.users = {u.email.lower(): u for u in users}

    async def get_by_email(self, email):
        return self.users.get(email.lower())

    async def update(self, user, update_dict):
        return user


def _manager():
    probe = UserManager(None)
    alice = SimpleNamespace(
        id=uuid.uuid4(), email="alice@example.com", is_active=True,
        hashed_password=probe.password_helper.hash(PASSWORD),
    )
    return UserManager(_UserDB([alice])), alice


def _login(manager, email, password):
    creds = SimpleNamespace(username=email, password=password)
    return asyncio.run(manager.authenticate(creds))


def test_account_locks_after_repeated_failures_even_for_correct_password(redis):
    manager, alice = _manager()
    for _ in range(LOGIN_FAILURE_LIMIT):
        assert _login(manager, alice.email, "wrong") is None
    with pytest.raises(HTTPException) as exc:
        _login(manager, alice.email, PASSWORD)
    assert exc.value.status_code == 429


def test_unknown_emails_are_throttled_the_same_way(redis):
    manager, _ = _manager()
    for _ in range(LOGIN_FAILURE_LIMIT):
        assert _login(manager, "nobody@example.com", "x") is None
    with pytest.raises(HTTPException):
        _login(manager, "nobody@example.com", "x")


def test_successful_logins_do_not_count(redis):
    manager, alice = _manager()
    for _ in range(LOGIN_FAILURE_LIMIT * 2):
        assert _login(manager, alice.email, PASSWORD) is alice


def test_lockout_is_per_account_and_case_insensitive(redis):
    manager, alice = _manager()
    for _ in range(LOGIN_FAILURE_LIMIT):
        _login(manager, "ALICE@example.com", "wrong")
    with pytest.raises(HTTPException):
        _login(manager, "alice@example.com", PASSWORD)
    assert _login(manager, "bob@example.com", "x") is None  # other accounts unaffected


def test_redis_keys_do_not_contain_email(redis):
    manager, alice = _manager()
    _login(manager, alice.email, "wrong")
    assert redis.store and all("alice" not in key for key in redis.store)


def test_no_redis_means_no_lockout(monkeypatch):
    monkeypatch.setattr(rate_limit, "_get_redis", lambda: None)
    manager, alice = _manager()
    for _ in range(LOGIN_FAILURE_LIMIT + 5):
        _login(manager, alice.email, "wrong")
    assert _login(manager, alice.email, PASSWORD) is alice


@pytest.mark.parametrize("hook", ["on_after_forgot_password", "on_after_request_verify"])
def test_emails_per_address_are_capped(redis, monkeypatch, hook):
    sent = []

    async def fake_send(to, *args, **kwargs):
        sent.append(to)

    monkeypatch.setattr(auth, "send_email", fake_send)
    manager, alice = _manager()
    for _ in range(EMAILS_PER_ADDRESS_LIMIT + 3):
        asyncio.run(getattr(manager, hook)(alice, "token"))
    assert len(sent) == EMAILS_PER_ADDRESS_LIMIT
