"""Input bounds: bounded upload reads, body-size middleware, schema limits,
and no blocking calls directly inside async route handlers."""
import ast
import asyncio
import io
import pathlib

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.api.uploads import read_upload_limited
from app.core.body_limit import BodySizeLimitMiddleware
from app.core.schemas import (
    MAX_ATTACHMENT_CHARS,
    MAX_MESSAGE_CHARS,
    AgentRequest,
    QueryRequest,
    TTSRequest,
)


class _CountingFile(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.bytes_read = 0

    def read(self, size=-1):
        chunk = super().read(size)
        self.bytes_read += len(chunk)
        return chunk


def _read(data: bytes, limit: int):
    f = _CountingFile(data)
    upload = UploadFile(file=f, filename="x.bin")
    return f, asyncio.run(read_upload_limited(upload, limit))


def test_read_upload_within_limit():
    _, data = _read(b"a" * 1000, 2000)
    assert data == b"a" * 1000


def test_read_upload_over_limit_stops_early():
    big = b"a" * (10 * 1024 * 1024)
    with pytest.raises(HTTPException) as exc:
        _read(big, 2 * 1024 * 1024)
    assert exc.value.status_code == 413


def test_read_upload_stops_reading_after_limit():
    f = _CountingFile(b"a" * (10 * 1024 * 1024))
    with pytest.raises(HTTPException):
        asyncio.run(read_upload_limited(UploadFile(file=f, filename="x"), 1024 * 1024))
    assert f.bytes_read <= 3 * 1024 * 1024  # never consumed the whole 10 MB


def _tiny_app(limit: int) -> TestClient:
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=limit)

    @app.post("/echo")
    async def echo(payload: dict):
        return {"ok": True}

    return TestClient(app)


def test_body_limit_rejects_large_declared_body():
    r = _tiny_app(100).post("/echo", content=b"x" * 500,
                            headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_body_limit_allows_small_body():
    r = _tiny_app(10_000).post("/echo", json={"a": 1})
    assert r.status_code == 200


def test_body_limit_sits_inside_cors():
    from fastapi.middleware.cors import CORSMiddleware

    from app.main import app

    order = [m.cls for m in app.user_middleware]  # outermost first
    assert order.index(CORSMiddleware) < order.index(BodySizeLimitMiddleware)


def test_schema_bounds():
    with pytest.raises(ValidationError):
        QueryRequest(question="q", top_k=0)
    with pytest.raises(ValidationError):
        QueryRequest(question="q", top_k=1000)
    with pytest.raises(ValidationError):
        QueryRequest(question="x" * (MAX_MESSAGE_CHARS + 1))
    with pytest.raises(ValidationError):
        AgentRequest(message="x" * (MAX_MESSAGE_CHARS + 1), session_id="s")
    with pytest.raises(ValidationError):
        TTSRequest(text="x" * (MAX_MESSAGE_CHARS + 1))
    assert QueryRequest(question="q", top_k=5).top_k == 5


def test_attachment_text_truncated_not_rejected():
    req = AgentRequest(message="hi", session_id="s", attachment_text="y" * (MAX_ATTACHMENT_CHARS + 500))
    assert len(req.attachment_text) == MAX_ATTACHMENT_CHARS


def test_admin_schema_bounds():
    from app.api.admin_routes import CorpusSearchRequest, UserDetailsUpdate

    with pytest.raises(ValidationError):
        CorpusSearchRequest(query="q", alpha=1.5)
    with pytest.raises(ValidationError):
        UserDetailsUpdate(display_name="n" * 81)


# Blocking helpers that must not be called directly from an async handler.
BLOCKING = {
    "ingest", "ingest_single_file_for_user", "extract_attachment", "transcribe_file",
    "add_to_global_corpus", "global_corpus_count", "global_search", "list_sources",
    "delete_by_source", "delete_user_collection", "delete_user_docs_dir",
    "delete_user_workspace_dir",
}


def _direct_blocking_calls(func: ast.AsyncFunctionDef) -> list[str]:
    found = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue  # nested helpers run in the threadpool
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) \
                    and child.func.id in BLOCKING:
                found.append(f"{func.name}: {child.func.id}() line {child.lineno}")
            visit(child)

    visit(func)
    return found


def test_async_handlers_offload_blocking_work():
    offenders = []
    for path in pathlib.Path("app/api").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                offenders += [f"{path.name} {o}" for o in _direct_blocking_calls(node)]
    assert not offenders, offenders
