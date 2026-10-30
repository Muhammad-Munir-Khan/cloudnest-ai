"""End-to-end smoke test against a running API: health, signup, login, chat.

Run AFTER starting the stack (see CLAUDE.md / README), e.g.:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    python scripts/smoke_test.py            # or: SMOKE_API=https://host python scripts/smoke_test.py

It registers a throwaway user (smoke-<random>@example.com), logs in for a bearer
token and calls the authenticated endpoints with it. Needs the LLM provider
configured; the model calls (/rag/query, /agent/chat) can take a while.

Limits: the user is not deleted afterwards (only an admin can delete users via
DELETE /admin/users/{id}); it fails at login if REQUIRE_EMAIL_VERIFICATION is on,
since a throwaway address cannot verify; and signup is rate limited (5/min/IP).
"""
import os
import sys
import uuid

import requests

API = os.environ.get("SMOKE_API", "http://localhost:8000").rstrip("/")
LLM_TIMEOUT = 300


class Smoke:
    def __init__(self) -> None:
        self.failures = 0
        self.headers: dict[str, str] = {}

    def check(self, name: str, response: requests.Response, ok=(200,), need=None) -> dict | list | None:
        """Print one step; count a failure on a bad status or a missing field."""
        print(f"\n=== {name} ===")
        body = None
        try:
            body = response.json()
        except ValueError:
            pass
        passed = response.status_code in ok
        if passed and need and not (isinstance(body, dict) and body.get(need)):
            print(f"missing or empty field: {need}")
            passed = False
        print(response.status_code, body if passed else response.text[:500])
        if not passed:
            self.failures += 1
        return body if passed else None

    def get(self, path: str, **kw) -> requests.Response:
        return requests.get(f"{API}{path}", headers=self.headers, timeout=kw.pop("timeout", 15), **kw)

    def post(self, path: str, timeout: int = 15, **kw) -> requests.Response:
        return requests.post(f"{API}{path}", headers=self.headers, timeout=timeout, **kw)


def main() -> int:
    s = Smoke()
    email = f"smoke-{uuid.uuid4().hex[:10]}@example.com"
    password = f"Smoke-{uuid.uuid4().hex[:12]}-1"

    s.check("GET /health/live", s.get("/health/live"))
    s.check("GET /health/ready", s.get("/health/ready"))

    # Unauthenticated calls must be refused (protects against an open API).
    s.check("GET /users/me without a token (expect 401)", s.get("/users/me"), ok=(401,))

    s.check("POST /auth/register", s.post("/auth/register", json={"email": email, "password": password}), ok=(201,))
    login = s.check(
        "POST /auth/jwt/login",
        s.post("/auth/jwt/login", data={"username": email, "password": password}),
        need="access_token",
    )
    if not login:
        print("\n✗ cannot continue without a token (is REQUIRE_EMAIL_VERIFICATION on?)")
        return s.failures
    s.headers = {"Authorization": f"Bearer {login['access_token']}"}

    me = s.check("GET /users/me", s.get("/users/me"), need="email")
    if me and me.get("email") != email:
        print("wrong user returned")
        s.failures += 1

    sid = str(uuid.uuid4())
    s.check(
        "POST /agent/chat",
        s.post("/agent/chat", json={"message": "What is 23 * 45?", "session_id": sid}, timeout=LLM_TIMEOUT),
        need="answer",
    )
    s.check(
        "POST /agent/chat (follow-up, tests memory)",
        s.post("/agent/chat", json={"message": "Now multiply that by 2.", "session_id": sid}, timeout=LLM_TIMEOUT),
        need="answer",
    )
    sessions = s.check("GET /agent/sessions", s.get("/agent/sessions"))
    if sessions is not None and not any(x.get("id") == sid for x in sessions):
        print("the chat session is not listed")
        s.failures += 1
    s.check("GET /agent/sessions/{id}/messages", s.get(f"/agent/sessions/{sid}/messages"))

    s.check("GET /rag/documents (new user, expect empty)", s.get("/rag/documents"))
    s.check(
        "POST /rag/query (no documents yet)",
        s.post("/rag/query", json={"question": "Summarize my documents in 2 sentences."}, timeout=LLM_TIMEOUT),
        need="answer",
    )

    print(f"\n{'✓ all checks passed' if s.failures == 0 else f'✗ {s.failures} failures'}")
    return s.failures


if __name__ == "__main__":
    sys.exit(main())
