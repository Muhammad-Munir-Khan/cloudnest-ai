"""Security response headers middleware for FastAPI.

Adds standard hardening headers to every response.

CSP is deliberately split: the Swagger UI (`/docs`, `/redoc`, `/openapi.json`)
loads scripts/styles and uses inline assets, so a strict `default-src 'none'`
would break it. Those paths get a relaxed CSP; everything else (the JSON API)
gets a strict one. For a JSON API behind a separate Next.js frontend the strict
CSP barely matters for the API itself, but it's defense-in-depth and makes the
API safe to open directly in a browser.

IMPORTANT: these headers belong on the FRONTEND too, where they matter more.
In particular the microphone permission must be ALLOWED on the frontend origin
(the voice mic button), so the frontend's Permissions-Policy must use
`microphone=(self)`. Setting `microphone=()` here on API responses is harmless
(the API has no mic surface) but the real control lives in the Next.js config —
see the headers() block to add to next.config. Do not copy `microphone=()` to
the frontend or the mic button will silently fail.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Strict default for the JSON API surface: deny everything, no framing.
_STRICT_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

# Relaxed CSP for the interactive docs only. Swagger UI ships inline JS/CSS and
# (by default) pulls assets from jsdelivr; allow just enough for it to render.
_DOCS_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'"
)

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardening headers to every response.

    Args:
        enable_hsts: send Strict-Transport-Security. Harmless over plain HTTP
            (browsers ignore HSTS on http://), effective once TLS is terminated
            in front of the app. Leave True for production.
    """

    def __init__(self, app, enable_hsts: bool = True):
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        path = request.url.path
        is_docs = any(path.startswith(p) for p in _DOCS_PATHS)

        # setdefault so we never clobber a header a route set intentionally.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy", _DOCS_CSP if is_docs else _STRICT_CSP
        )

        if self.enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )

        return response
