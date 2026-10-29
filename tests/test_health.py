"""Liveness and readiness probes (app/main.py)."""
import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_main():
    import app.main as main
    return main


def _ok():
    async def check():
        return "ok"
    return check


def _fail(exc=RuntimeError("down")):
    async def check():
        raise exc
    return check


def _hang():
    async def check():
        await asyncio.sleep(60)
    return check


def test_live_checks_nothing_external(app_main):
    r = TestClient(app_main.app).get("/health/live")
    assert r.status_code == 200 and r.json()["status"] == "alive"


def test_ready_when_all_dependencies_ok(app_main, monkeypatch):
    for name in ("_check_postgres", "_check_redis", "_check_weaviate"):
        monkeypatch.setattr(app_main, name, _ok())
    r = TestClient(app_main.app).get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready",
                        "components": {"postgres": "ok", "redis": "ok", "weaviate": "ok"}}


def test_not_ready_when_postgres_fails(app_main, monkeypatch):
    monkeypatch.setattr(app_main, "_check_postgres", _fail())
    monkeypatch.setattr(app_main, "_check_redis", _ok())
    monkeypatch.setattr(app_main, "_check_weaviate", _ok())
    r = TestClient(app_main.app).get("/health/ready")
    assert r.status_code == 503
    assert r.json()["components"]["postgres"] == "error: RuntimeError"


def test_redis_and_weaviate_failures_only_degrade(app_main, monkeypatch):
    monkeypatch.setattr(app_main, "_check_postgres", _ok())
    monkeypatch.setattr(app_main, "_check_redis", _fail())
    monkeypatch.setattr(app_main, "_check_weaviate", _fail(ConnectionError("x")))
    r = TestClient(app_main.app).get("/health/ready")
    assert r.status_code == 200
    assert r.json()["components"]["weaviate"] == "error: ConnectionError"


def test_hung_dependency_times_out_instead_of_hanging(app_main, monkeypatch):
    monkeypatch.setattr(app_main, "_check_postgres", _ok())
    monkeypatch.setattr(app_main, "_check_redis", _hang())  # 3 s timeout
    monkeypatch.setattr(app_main, "_check_weaviate", _ok())
    r = TestClient(app_main.app).get("/health/ready")
    assert r.status_code == 200
    assert r.json()["components"]["redis"] == "error: timeout"
