"""Runtime flags are read through Settings, so .env applies in every run mode.

Before CFG-02, REDIS_URL, COOKIE_SECURE, REQUIRE_EMAIL_VERIFICATION, the
Sentry settings and RATE_LIMIT_FAIL_OPEN were read with os.getenv, which
ignores .env unless Docker exported it into the process environment.
"""
import ast
import pathlib
import re

import pytest

from app.core.config import Settings

RUNTIME_KEYS = [
    "REDIS_URL", "RATE_LIMIT_FAIL_OPEN", "COOKIE_SECURE", "REQUIRE_EMAIL_VERIFICATION",
    "SENTRY_DSN", "ENVIRONMENT", "SENTRY_TRACES_SAMPLE_RATE",
]
TEMPLATE = pathlib.Path(".env.example").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_process_env(monkeypatch):
    # Make sure only the .env file under test supplies these values.
    for key in RUNTIME_KEYS:
        monkeypatch.delenv(key, raising=False)


def _template_without_runtime_keys() -> str:
    pattern = re.compile(rf"^({'|'.join(RUNTIME_KEYS)})=.*$", re.MULTILINE | re.IGNORECASE)
    return pattern.sub("", TEMPLATE)


def test_runtime_flags_load_from_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        _template_without_runtime_keys()
        + "\nREDIS_URL=redis://cache.internal:6380/2\nRATE_LIMIT_FAIL_OPEN=false\n"
        "COOKIE_SECURE=true\nREQUIRE_EMAIL_VERIFICATION=true\n"
        "SENTRY_DSN=https://key@sentry.example/1\nENVIRONMENT=staging\n"
        "SENTRY_TRACES_SAMPLE_RATE=0.5\n",
        encoding="utf-8",
    )
    s = Settings(_env_file=env)
    assert s.REDIS_URL == "redis://cache.internal:6380/2"
    assert s.rate_limit_fail_open is False
    assert s.COOKIE_SECURE is True
    assert s.REQUIRE_EMAIL_VERIFICATION is True
    assert s.SENTRY_DSN == "https://key@sentry.example/1"
    assert s.ENVIRONMENT == "staging"
    assert s.SENTRY_TRACES_SAMPLE_RATE == 0.5


def test_runtime_flags_default_to_previous_fallbacks(tmp_path):
    env = tmp_path / ".env"
    env.write_text(_template_without_runtime_keys(), encoding="utf-8")
    s = Settings(_env_file=env)
    assert s.REDIS_URL == "redis://redis:6379/0"
    assert s.rate_limit_fail_open is True
    assert s.COOKIE_SECURE is False
    assert s.REQUIRE_EMAIL_VERIFICATION is False
    assert s.SENTRY_DSN == ""
    assert s.ENVIRONMENT == "development"
    assert s.SENTRY_TRACES_SAMPLE_RATE == 0.1


def test_app_code_does_not_read_os_environment_directly():
    """Config must go through Settings; only the secrets helper reads env."""
    offenders = []
    for path in pathlib.Path("app").rglob("*.py"):
        if path.name == "secrets.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id == "os" and node.attr in ("getenv", "environ"):
                offenders.append(f"{path}:{node.lineno}")
    assert not offenders, offenders
