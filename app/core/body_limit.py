"""Reject oversized request bodies before they are parsed.

Pure ASGI middleware: if the declared Content-Length exceeds the limit, answer
413 without reading the body (so multipart parsing never starts). Bodies sent
with chunked transfer encoding carry no Content-Length; those are bounded by
the per-route read limits (app/api/uploads.py) and, in production, by the
reverse proxy's request_body max_size (docker/Caddyfile).
"""
import json

# Largest legitimate request is a 25 MB knowledge-base upload plus multipart
# overhead.
DEFAULT_MAX_BODY_BYTES = 30 * 1024 * 1024


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int = DEFAULT_MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            for name, value in scope.get("headers", []):
                if name == b"content-length":
                    try:
                        declared = int(value)
                    except ValueError:
                        declared = None
                    if declared is not None and declared > self.max_bytes:
                        await self._reject(send)
                        return
                    break
        await self.app(scope, receive, send)

    async def _reject(self, send):
        body = json.dumps({
            "detail": f"Request body too large. Max {self.max_bytes // (1024 * 1024)} MB."
        }).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
