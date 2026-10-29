"""Security-focused tests for the Phase 1 hardening.

Every test exercises the real application code (no copied logic):
upload signature sniffing, rate-limit client keying, the Sentry DSN guard,
the secrets loader, and the security-headers middleware. None of them need a
network, database or Redis.
"""
import pytest

from app.api.attachment_routes import _sniff_ok
from app.core import rate_limit
from app.core.config import settings
from app.core.observability import sentry_dsn_is_valid


# --------------------------------------------------------------------------- #
# Upload signature sniffing (app/api/attachment_routes.py::_sniff_ok)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "ext,data,expected",
    [
        (".pdf", b"%PDF-1.7\n...", True),
        (".pdf", b"MZ\x90\x00 not a pdf", False),       # spoofed pdf rejected
        (".png", b"\x89PNG\r\n\x1a\n....", True),
        (".png", b"GIF89a not a png", False),            # wrong image type
        (".jpg", b"\xff\xd8\xff\xe0....", True),
        (".jpeg", b"not a jpeg", False),
        (".gif", b"GIF89a....", True),
        (".webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ", True),
        (".webp", b"RIFF\x00\x00\x00\x00AVI ", False),   # RIFF but not WEBP
        (".txt", b"anything goes for text", True),       # text has no signature
    ],
)
def test_sniff_ok(ext, data, expected):
    assert _sniff_ok(ext, data) is expected


# --------------------------------------------------------------------------- #
# Rate-limit client keying (app/core/rate_limit.py::_client_key)
# XFF / trusted-proxy cases are covered in tests/test_rate_limit.py.
# --------------------------------------------------------------------------- #
class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeState:
    pass


class _FakeRequest:
    """Minimal stand-in matching the attributes _client_key reads."""
    def __init__(self, headers=None, client_host="1.2.3.4", user=None):
        self.headers = headers or {}
        self.client = _FakeClient(client_host)
        self.state = _FakeState()
        if user is not None:
            self.state.user = user


@pytest.fixture
def no_trusted_proxies(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", "")
    rate_limit._trusted_networks.cache_clear()
    yield
    rate_limit._trusted_networks.cache_clear()


def test_client_key_prefers_authenticated_user(no_trusted_proxies):
    class U:
        id = "abc-123"
    assert rate_limit._client_key(_FakeRequest(user=U())) == "user:abc-123"


def test_client_key_falls_back_to_direct_ip(no_trusted_proxies):
    assert rate_limit._client_key(_FakeRequest(client_host="9.9.9.9")) == "ip:9.9.9.9"


def test_client_key_ignores_xff_from_untrusted_peer(no_trusted_proxies):
    req = _FakeRequest(headers={"x-forwarded-for": "203.0.113.5"}, client_host="9.9.9.9")
    assert rate_limit._client_key(req) == "ip:9.9.9.9"


# --------------------------------------------------------------------------- #
# Sentry DSN guard (app/core/observability.py::sentry_dsn_is_valid)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "dsn,expected",
    [
        ("", False),
        ("   ", False),
        (None, False),
        ("YOUR_DSN_HERE", False),
        ("changeme", False),
        ("https://abc@o1.ingest.sentry.io/2", True),
        ("http://localhost/1", True),
    ],
)
def test_sentry_dsn_guard(dsn, expected):
    assert sentry_dsn_is_valid(dsn) is expected


def test_init_sentry_disabled_without_dsn(monkeypatch):
    from app.core.observability import init_sentry

    monkeypatch.setenv("SENTRY_DSN", "not-a-url")
    assert init_sentry() is False


# --------------------------------------------------------------------------- #
# Secrets loader (app/core/secrets.py) — file > docker-secret > env > default
# --------------------------------------------------------------------------- #
def test_secret_from_file_env(tmp_path, monkeypatch):
    from app.core.secrets import get_secret

    secret_file = tmp_path / "jwt.txt"
    secret_file.write_text("  super-secret-value\n")
    monkeypatch.setenv("JWT_SECRET_FILE", str(secret_file))
    monkeypatch.delenv("JWT_SECRET", raising=False)
    assert get_secret("JWT_SECRET") == "super-secret-value"  # stripped


def test_secret_from_plain_env(monkeypatch):
    from app.core.secrets import get_secret

    monkeypatch.delenv("JWT_SECRET_FILE", raising=False)
    monkeypatch.setenv("JWT_SECRET", "env-value")
    assert get_secret("JWT_SECRET") == "env-value"


def test_secret_required_raises_when_missing(monkeypatch):
    from app.core.secrets import SecretNotFoundError, get_secret

    monkeypatch.delenv("DOES_NOT_EXIST_FILE", raising=False)
    monkeypatch.delenv("DOES_NOT_EXIST", raising=False)
    with pytest.raises(SecretNotFoundError):
        get_secret("DOES_NOT_EXIST", required=True)


def test_secret_default_when_missing(monkeypatch):
    from app.core.secrets import get_secret

    monkeypatch.delenv("NOPE_FILE", raising=False)
    monkeypatch.delenv("NOPE", raising=False)
    assert get_secret("NOPE", default="fallback") == "fallback"


# --------------------------------------------------------------------------- #
# Security headers middleware (app/core/security_headers.py)
# --------------------------------------------------------------------------- #
def test_security_headers_present_on_responses():
    import fastapi
    from fastapi.testclient import TestClient

    from app.core.security_headers import SecurityHeadersMiddleware

    app = fastapi.FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    r = TestClient(app).get("/ping")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" in r.headers
    # Strict CSP on a normal (non-docs) route.
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]
