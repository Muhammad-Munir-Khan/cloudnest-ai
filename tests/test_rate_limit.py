"""Rate limiter: client IP resolution and route coverage."""
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute

from app.core import rate_limit
from app.core.config import settings
from app.core.rate_limit import RateLimiter, _client_key


def _request(peer: str, xff: str | None = None):
    headers = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer), state=SimpleNamespace())


@pytest.fixture
def trusted(monkeypatch):
    def _set(value: str):
        monkeypatch.setattr(settings, "trusted_proxies", value)
        rate_limit._trusted_networks.cache_clear()
    yield _set
    rate_limit._trusted_networks.cache_clear()


def test_spoofed_xff_ignored_without_trusted_proxy(trusted):
    trusted("")
    assert _client_key(_request("203.0.113.9", "1.1.1.1")) == "ip:203.0.113.9"


def test_spoofed_xff_ignored_from_untrusted_peer(trusted):
    trusted("172.16.0.0/12")
    assert _client_key(_request("203.0.113.9", "1.1.1.1")) == "ip:203.0.113.9"


def test_xff_used_from_trusted_proxy(trusted):
    trusted("172.16.0.0/12")
    assert _client_key(_request("172.18.0.5", "198.51.100.7")) == "ip:198.51.100.7"


def test_client_prepended_fake_hop_is_ignored(trusted):
    # Client sends "X-Forwarded-For: 1.1.1.1"; the proxy appends the real IP.
    trusted("172.16.0.0/12")
    key = _client_key(_request("172.18.0.5", "1.1.1.1, 198.51.100.7"))
    assert key == "ip:198.51.100.7"


def test_chain_of_trusted_proxies(trusted):
    trusted("172.16.0.0/12,10.0.0.0/8")
    key = _client_key(_request("172.18.0.5", "198.51.100.7, 10.0.0.2"))
    assert key == "ip:198.51.100.7"


def test_invalid_trusted_entry_is_ignored(trusted):
    trusted("not-an-ip, 172.16.0.0/12")
    assert _client_key(_request("172.18.0.5", "198.51.100.7")) == "ip:198.51.100.7"


# Routes intentionally without a limiter: health probes, root, API docs.
UNLIMITED = {"/", "/health", "/health/live", "/health/ready"}


def _has_limiter(dependant) -> bool:
    for dep in dependant.dependencies:
        if isinstance(dep.call, RateLimiter) or _has_limiter(dep):
            return True
    return False


def test_every_route_is_rate_limited():
    from app.main import app

    missing = [
        f"{sorted(r.methods)} {r.path}"
        for r in app.routes
        if isinstance(r, APIRoute)
        and r.path not in UNLIMITED
        and not r.path.startswith(("/docs", "/redoc", "/openapi"))
        and not _has_limiter(r.dependant)
    ]
    assert not missing, f"routes without a rate limiter: {missing}"
