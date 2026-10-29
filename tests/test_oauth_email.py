"""OAuth account linking requires a provider-verified email (SEC-12)."""
import asyncio
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi_users import exceptions as fu_exceptions
from fastapi_users.router.oauth import generate_state_token

from app.core.config import settings
from app.core.oauth_email import provider_email_verified


def _transport(payload=None, status=200, raises=False):
    def handler(request):
        if raises:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(status, json=payload)
    return httpx.MockTransport(handler)


def _check(provider, email, **kw):
    return asyncio.run(provider_email_verified(provider, "tok", email, transport=_transport(**kw)))


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"email": "a@x.com", "email_verified": True}, True),
        ({"email": "A@X.com", "email_verified": True}, True),     # case-insensitive
        ({"email": "a@x.com", "email_verified": False}, False),
        ({"email": "other@x.com", "email_verified": True}, False),  # different address
        ({"email": "a@x.com"}, False),                             # flag missing
    ],
)
def test_google(payload, expected):
    assert _check("google", "a@x.com", payload=payload) is expected


@pytest.mark.parametrize(
    "payload,expected",
    [
        ([{"email": "a@x.com", "primary": True, "verified": True}], True),
        ([{"email": "a@x.com", "primary": True, "verified": False}], False),
        ([{"email": "b@x.com", "verified": True}, {"email": "a@x.com", "verified": False}], False),
        ([{"email": "b@x.com", "verified": True}], False),
    ],
)
def test_github(payload, expected):
    assert _check("github", "a@x.com", payload=payload) is expected


def test_failures_count_as_unverified():
    assert _check("github", "a@x.com", raises=True) is False
    assert _check("google", "a@x.com", payload={"error": "x"}, status=401) is False
    assert _check("unknown", "a@x.com", payload={}) is False
    assert _check("google", "", payload={"email": "", "email_verified": True}) is False


# --- _finish_oauth wiring ----------------------------------------------------

class _FakeManager:
    def __init__(self, raise_exists=False):
        self.kwargs = None
        self.raise_exists = raise_exists

    async def oauth_callback(self, *args, **kwargs):
        self.kwargs = kwargs
        if self.raise_exists:
            raise fu_exceptions.UserAlreadyExists()
        return SimpleNamespace(id=uuid.uuid4(), is_active=True, display_name="Existing Name")


@pytest.fixture
def finish(monkeypatch):
    import app.main as main

    class FakeClient:
        async def get_id_email(self, token):
            return "12345", "victim@example.com"

    monkeypatch.setitem(main._oauth_clients, "github", FakeClient())
    state = generate_state_token({}, settings.jwt_secret)

    def run(verified: bool, manager: _FakeManager):
        async def fake_verified(*a, **k):
            return verified
        monkeypatch.setattr(main, "provider_email_verified", fake_verified)
        token = {"access_token": "tok"}
        return asyncio.run(main._finish_oauth("github", None, (token, state), manager))

    return run


def test_verified_email_may_link_and_is_marked_verified(finish):
    manager = _FakeManager()
    resp = finish(True, manager)
    assert manager.kwargs == {"associate_by_email": True, "is_verified_by_default": True}
    assert resp.status_code == 302 and resp.headers["location"].endswith("/chat")


def test_unverified_email_never_links(finish):
    manager = _FakeManager()
    finish(False, manager)
    assert manager.kwargs == {"associate_by_email": False, "is_verified_by_default": False}


def test_unverified_email_clashing_with_account_redirects_to_login(finish):
    resp = finish(False, _FakeManager(raise_exists=True))
    assert resp.status_code == 302
    assert "/login?error=" in resp.headers["location"]
    assert "set-cookie" not in resp.headers  # no session issued
