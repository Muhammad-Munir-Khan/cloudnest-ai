"""End-to-end smoke test: hits every endpoint to verify the system is healthy.

Run AFTER starting the API with:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import sys
import uuid

import requests

API = "http://localhost:8000"


def step(name: str) -> None:
    print(f"\n=== {name} ===")


def main() -> int:
    failures = 0

    step("GET /health")
    r = requests.get(f"{API}/health", timeout=10)
    print(r.status_code, r.json())
    if r.status_code != 200:
        failures += 1

    step("POST /rag/query")
    r = requests.post(
        f"{API}/rag/query",
        json={"question": "Summarize the documents in 2 sentences."},
        timeout=300,
    )
    print(r.status_code, r.json() if r.status_code < 400 else r.text)
    if r.status_code != 200:
        failures += 1

    step("POST /agent/chat")
    sid = str(uuid.uuid4())
    r = requests.post(
        f"{API}/agent/chat",
        json={"message": "What is 23 * 45?", "session_id": sid},
        timeout=300,
    )
    print(r.status_code, r.json() if r.status_code < 400 else r.text)
    if r.status_code != 200:
        failures += 1

    step("POST /agent/chat (follow-up, tests memory)")
    r = requests.post(
        f"{API}/agent/chat",
        json={"message": "Now multiply that by 2.", "session_id": sid},
        timeout=300,
    )
    print(r.status_code, r.json() if r.status_code < 400 else r.text)
    if r.status_code != 200:
        failures += 1

    print(f"\n{'✓ all checks passed' if failures == 0 else f'✗ {failures} failures'}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
