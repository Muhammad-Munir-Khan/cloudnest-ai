"""Redis-backed rate limiting for FastAPI.

A fixed-window counter keyed by the authenticated user id when available,
otherwise the client IP. X-Forwarded-For is only honoured when the direct peer
is a trusted proxy (TRUSTED_PROXIES); otherwise any client could rotate the
header to dodge limits. Used as a route dependency:

    from app.core.rate_limit import RateLimiter

    @router.post(
        "/query",
        dependencies=[Depends(RateLimiter(times=30, seconds=60, scope="rag"))],
    )
    async def query(...): ...

Design choices:
  - **Fail-open.** If Redis is unreachable the request is allowed and a warning
    is logged. For a limiter, availability is normally preferred over strict
    enforcement (don't take the whole app down because Redis blipped). Flip
    `_FAIL_OPEN = False` to fail closed (return 503) instead.
  - **Fixed window.** Simple and cheap (one INCR + one EXPIRE). It allows a
    burst at the window boundary; that's acceptable for a first cut. Upgrade to
    a sliding-window or token-bucket later if boundary bursts matter.

Config (app/core/config.py Settings; env, .env or /run/secrets):
  REDIS_URL                 default redis://redis:6379/0
  RATE_LIMIT_FAIL_OPEN      default true (settings field rate_limit_fail_open)
  TRUSTED_PROXIES           comma-separated IPs/CIDRs of reverse proxies whose
                            X-Forwarded-For may be trusted (settings field
                            trusted_proxies; default empty = trust none)

Requires the `redis` package (redis-py, async client): add `redis>=5` to
requirements.txt, and a `redis` service to docker-compose (see README/below).
"""
import ipaddress
import time
from functools import lru_cache

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

try:
    from redis import asyncio as aioredis
except ImportError:  # redis not installed yet — limiter degrades to no-op
    aioredis = None

REDIS_URL = settings.REDIS_URL
_FAIL_OPEN = settings.rate_limit_fail_open

_redis = None


def _get_redis():
    """Lazy singleton async Redis client. Returns None if redis isn't installed."""
    global _redis
    if aioredis is None:
        return None
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    return _redis


@lru_cache(maxsize=1)
def _trusted_networks() -> tuple:
    """Parse settings.trusted_proxies once into ip_network objects."""
    nets = []
    for raw in (settings.trusted_proxies or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            nets.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            log.warning("ignoring invalid TRUSTED_PROXIES entry %r", raw)
    return tuple(nets)


def _is_trusted_proxy(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _trusted_networks())


def _client_ip(request: Request) -> str:
    """Real client IP, honouring X-Forwarded-For only from trusted proxies.

    If the direct peer is not a trusted proxy, its address is the client and
    any X-Forwarded-For header is ignored (it is client-controlled). If it is
    trusted, walk the X-Forwarded-For chain from the right (nearest hop) and
    return the first address that is not itself a trusted proxy.
    """
    peer = request.client.host if request.client else "unknown"
    xff = request.headers.get("x-forwarded-for")
    if not xff or not _is_trusted_proxy(peer):
        return peer
    hops = [h.strip() for h in xff.split(",") if h.strip()]
    for hop in reversed(hops):
        if not _is_trusted_proxy(hop):
            return hop
    return hops[0] if hops else peer


def _client_key(request: Request) -> str:
    """Identify the caller: authenticated user if present, else client IP.

    request.state.user is honoured if something sets it; router-level limiter
    dependencies run before authentication, so in practice keying is by IP.
    """
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None) if user is not None else None
    if user_id is not None:
        return f"user:{user_id}"
    return f"ip:{_client_ip(request)}"


class RateLimiter:
    """Dependency factory limiting to `times` requests per `seconds` window.

    `scope` namespaces the counter so different endpoint groups (auth, rag,
    agent) get independent budgets for the same caller.
    """

    def __init__(self, times: int, seconds: int, scope: str = "default"):
        self.times = times
        self.seconds = seconds
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        r = _get_redis()
        if r is None:
            if _FAIL_OPEN:
                return
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "rate limiter unavailable"
            )

        window = int(time.time() // self.seconds)
        key = f"rl:{self.scope}:{_client_key(request)}:{window}"

        try:
            current = await r.incr(key)
            if current == 1:
                await r.expire(key, self.seconds)
        except Exception as e:
            log.warning(
                "rate limiter Redis error (failing %s): %s",
                "open" if _FAIL_OPEN else "closed",
                e,
            )
            if _FAIL_OPEN:
                return
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "rate limiter error"
            )

        if current > self.times:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: max {self.times} requests per {self.seconds}s.",
                headers={"Retry-After": str(self.seconds)},
            )