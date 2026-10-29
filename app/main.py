"""FastAPI application entry point."""
import os
from contextlib import asynccontextmanager

import httpx
import jwt as pyjwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.security_headers import SecurityHeadersMiddleware
from app.core.rate_limit import RateLimiter
from fastapi_users.jwt import decode_jwt
from fastapi_users.router.oauth import generate_state_token
from httpx_oauth.integrations.fastapi import OAuth2AuthorizeCallback
from sqlalchemy import update

from app import __version__
from app.api import agent_routes, attachment_routes, rag_routes, voice_routes, admin_routes
from app.core.auth import (
    AccountSuspendedError,
    cookie_backend,
    current_active_user,
    fastapi_users,
    get_user_manager,
    github_oauth_client,
    google_oauth_client,
    jwt_backend,
)
from app.core.config import settings
from app.core.db import get_async_session
from app.core.llm import active_model_name, active_provider
from app.core.logging import configure_logging, get_logger
from app.core.schemas_user import UserCreate, UserRead, UserUpdate
from app.models.user import User

configure_logging()
log = get_logger(__name__)


# --- Error tracking (Sentry) --------------------------------------------------
# No-op unless SENTRY_DSN is a real http(s):// URL, and a no-op if sentry-sdk
# isn't installed. We validate the DSN scheme rather than just truthiness so a
# blank, placeholder, or malformed value can NEVER crash startup (sentry_sdk
# raises BadDsn on init for an invalid DSN). send_default_pii=False keeps user
# emails / IPs out of error reports.
_SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
if _SENTRY_DSN.startswith(("http://", "https://")):
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            environment=os.getenv("ENVIRONMENT", "development"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,
        )
        log.info("Sentry error tracking enabled (env=%s)", os.getenv("ENVIRONMENT", "development"))
    except ImportError:
        log.info("sentry-sdk not installed; error tracking disabled")
    except Exception as e:
        # Never let observability setup take down the app.
        log.warning("Sentry init failed, continuing without it: %s", e)
else:
    log.info("SENTRY_DSN not set or not a URL; error tracking disabled")


# --- Startup pre-warm ---------------------------------------------------------
# BGE-M3 is ~2.2GB on first download. Without pre-warming, the FIRST user
# request that needs embeddings (upload, RAG query) sits silently while the
# model downloads from HuggingFace - looks like the system is broken.
#
# We embed one dummy string at startup so:
#   1. The download happens during container boot (visible in logs)
#   2. The model lives in get_embeddings()'s lru_cache for the container's life
#   3. The first real user request answers in normal time
#
# If the model is already cached on disk (subsequent container restarts), this
# adds ~1 second to startup - acceptable.

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: pre-warm the embedder, then serve."""
    log.info("pre-warming embedding model: %s", settings.embedding_model)
    try:
        from app.rag.embeddings import get_embeddings
        embedder = get_embeddings()
        _ = embedder.embed_query("warmup")
        log.info(
            "embedding model ready: %s (1 warmup vector produced)",
            settings.embedding_model,
        )
    except Exception as e:
        log.error(
            "embedding pre-warm FAILED for %s: %s. RAG/KB upload will "
            "trigger an on-demand download on first use.",
            settings.embedding_model, e,
        )
    yield


app = FastAPI(
    title="GenAI Conversational Automation Agent",
    description="RAG + Agent + Voice. Multi-tenant, Postgres-backed.",
    version=__version__,
    lifespan=lifespan,
)

# --- CORS --------------------------------------------------------------------
# With allow_credentials=True, allow_origins CANNOT be ["*"] (browsers reject
# it). We normalize whatever settings exposes into an explicit list, accepting
# either the refactored `cors_origins_list` property or a comma-separated
# `cors_origins` string (or a plain list), so this is robust to the config
# shape. Lock this to your real frontend origin(s) in .env for production.
_cors_origins = getattr(settings, "cors_origins_list", None)
if _cors_origins is None:
    _raw_origins = settings.cors_origins
    if isinstance(_raw_origins, str):
        _cors_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
    else:
        _cors_origins = list(_raw_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    max_age=3600,  # cache preflight for an hour
)

# --- Security headers --------------------------------------------------------
# Adds nosniff / frame-deny / referrer-policy / permissions-policy / HSTS / CSP
# to every response. HSTS is harmless over plain HTTP and effective once TLS is
# terminated in front of the app. See app/core/security_headers.py for the CSP
# split that keeps the Swagger UI working.
app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True)


# --- Exception handlers ------------------------------------------------------

@app.exception_handler(AccountSuspendedError)
async def _handle_account_suspended(request: Request, exc: AccountSuspendedError):
    """Login attempt by a user whose is_active=False.

    Raised from UserManager.authenticate when the password is correct but the
    account is suspended. We deliberately do NOT include the admin-set reason
    here - the reason was already sent to the user by email at block time.
    Keeping it out of the API response means automated probes (and
    rate-limited brute-force tooling) can't enumerate suspension reasons.
    """
    return JSONResponse(
        status_code=403,
        content={
            "detail": (
                "Your account has been suspended. Check your email for "
                "details, or contact your administrator."
            )
        },
    )


# --- Application routes ------------------------------------------------------
# Rate limits are attached per-router (IP-based via Redis; fail-open if Redis is
# down). Limits are generous enough not to trip normal use — including the
# frontend's session polling — but stop abuse. Tune the numbers as needed.
# NOTE: keying is per-IP for now (router-level deps run before auth populates
# the user); for per-user limits, attach RateLimiter as a route-level dependency
# after current_active_user.
app.include_router(
    rag_routes.router,
    dependencies=[Depends(RateLimiter(times=60, seconds=60, scope="rag"))],
)
app.include_router(
    agent_routes.router,
    dependencies=[Depends(RateLimiter(times=120, seconds=60, scope="agent"))],
)
app.include_router(
    voice_routes.router,
    dependencies=[Depends(RateLimiter(times=30, seconds=60, scope="voice"))],
)
app.include_router(
    attachment_routes.router,
    dependencies=[Depends(RateLimiter(times=30, seconds=60, scope="attachments"))],
)
app.include_router(
    admin_routes.router,
    dependencies=[Depends(RateLimiter(times=120, seconds=60, scope="admin"))],
)
# --- Auth routes -------------------------------------------------------------
# Two login backends mounted under different prefixes:
#   POST /auth/jwt/login     -> returns {access_token, token_type} JSON (for API/curl)
#   POST /auth/cookie/login  -> sets httpOnly cookie, returns 204 No Content (for browser)
#   POST /auth/jwt/logout    -> no-op (JWT is stateless)
#   POST /auth/cookie/logout -> clears the cookie
#
# REQUIRE_EMAIL_VERIFICATION (env, default false): when true, both login
# backends reject unverified accounts (400) until the user clicks the link in
# their verification email. Left OFF by default so it doesn't lock out existing
# users or break dev where SMTP isn't configured. Turn it ON for production
# once SMTP works and the frontend has a /verify-email page. OAuth signups are
# created verified, so they're unaffected.
_REQUIRE_VERIFY = os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() in (
    "1", "true", "yes",
)
# Brute-force protection: 10 auth attempts/min/IP (login + logout share the
# router), 5 registrations/min/IP to curb signup spam.
app.include_router(
    fastapi_users.get_auth_router(jwt_backend, requires_verification=_REQUIRE_VERIFY),
    prefix="/auth/jwt",
    tags=["auth"],
    dependencies=[Depends(RateLimiter(times=10, seconds=60, scope="auth"))],
)
app.include_router(
    fastapi_users.get_auth_router(cookie_backend, requires_verification=_REQUIRE_VERIFY),
    prefix="/auth/cookie",
    tags=["auth"],
    dependencies=[Depends(RateLimiter(times=10, seconds=60, scope="auth"))],
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(RateLimiter(times=5, seconds=60, scope="register"))],
)
# Both routers can trigger outgoing email (forgot-password, request-verify-
# token), so they are throttled to curb email flooding and token guessing.
app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(RateLimiter(times=5, seconds=60, scope="password_reset"))],
)
app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(RateLimiter(times=5, seconds=60, scope="verify"))],
)

# =============================================================================
# OAuth (Google + GitHub) with post-login redirect to the frontend.
#
# fastapi-users 14's get_oauth_router callback returns 204 No Content, which
# strands the browser on the backend after the provider redirects back. OAuth
# is a full-page redirect flow, so we need the callback to:
#   1. Exchange the code for an access token (httpx-oauth)
#   2. Get/create/link the user (fastapi-users user_manager.oauth_callback)
#   3. Fetch the user's name from the provider userinfo endpoint and set it
#      on the user row IF display_name is currently empty (first signup
#      behavior - never overwrite a name the user has manually set)
#   4. Set the httpOnly auth cookie (cookie_backend's strategy + transport)
#   5. 302-redirect the browser to the frontend /chat page
#
# We reuse fastapi-users' own components (no reimplementation of OAuth or JWT
# logic) so the security guarantees match the built-in router exactly:
#   - CSRF state token is generated + verified (generate_state_token/decode_jwt)
#   - User get/create/link handled by user_manager.oauth_callback
#   - Cookie issued by the same cookie_backend strategy + transport as
#     POST /auth/cookie/login, with identical attributes
# =============================================================================

_OAUTH_STATE_AUDIENCE = "fastapi-users:oauth-state"

_oauth_clients = {
    "google": google_oauth_client,
    "github": github_oauth_client,
}

_oauth_callbacks = {
    "google": OAuth2AuthorizeCallback(
        google_oauth_client,
        redirect_url=f"{settings.backend_url}/auth/google/callback",
    ),
    "github": OAuth2AuthorizeCallback(
        github_oauth_client,
        redirect_url=f"{settings.backend_url}/auth/github/callback",
    ),
}

_oauth_scopes = {
    "google": ["openid", "email", "profile"],
    "github": ["user:email"],
}


# --- Provider userinfo fetchers -----------------------------------------------
# Each returns the user's preferred display name from the provider, or None if
# we couldn't get one. Failures are non-fatal: a missing name just means the
# user shows up with NULL display_name (status quo before this code existed).

async def _fetch_google_name(access_token: str) -> str | None:
    """Get the user's full name from Google's OIDC userinfo endpoint.

    Google guarantees the `name` field on real accounts when the `profile`
    scope was granted (we request it). Returns None on any failure.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                log.warning(
                    "Google userinfo failed: status=%d body=%r",
                    resp.status_code, resp.text[:200],
                )
                return None
            data = resp.json()
            name = (data.get("name") or "").strip()
            return name or None
    except Exception as e:
        log.warning("Google userinfo fetch error: %s", e)
        return None


async def _fetch_github_name(access_token: str) -> str | None:
    """Get the user's preferred display name from GitHub's user endpoint.

    GitHub's `name` field is the user's set display name. It can be NULL if
    they never set one. Fall back to `login` (their @username) - it's what
    GitHub itself shows in comments when name is empty.

    Returns None if both fields are missing (rare; bot accounts mostly).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if resp.status_code != 200:
                log.warning(
                    "GitHub user fetch failed: status=%d body=%r",
                    resp.status_code, resp.text[:200],
                )
                return None
            data = resp.json()
            # name -> login -> None
            name = (data.get("name") or "").strip()
            if name:
                return name
            login = (data.get("login") or "").strip()
            return login or None
    except Exception as e:
        log.warning("GitHub user fetch error: %s", e)
        return None


_PROVIDER_NAME_FETCHERS = {
    "google": _fetch_google_name,
    "github": _fetch_github_name,
}


async def _maybe_set_display_name(
    user: User, provider: str, access_token: str
) -> None:
    """Populate display_name from the OAuth provider on first signup.

    Rules:
      - If display_name is already set (any non-empty string), do NOT overwrite.
        The user may have manually edited it via the profile page; their
        choice wins.
      - If display_name is empty/NULL, fetch from provider. If the fetch
        returns a usable string, UPDATE the row. If it returns None, leave
        the user with NULL display_name (status quo).
      - Provider fetch failure is non-fatal. We log a warning and let the
        login complete normally.
    """
    existing = (user.display_name or "").strip()
    if existing:
        return  # respect manual edits, do not clobber

    fetcher = _PROVIDER_NAME_FETCHERS.get(provider)
    if fetcher is None:
        return  # unknown provider; nothing to do

    fetched = await fetcher(access_token)
    if not fetched:
        return  # provider gave us nothing usable

    # Write through a fresh session so we don't interfere with the user_manager
    # session lifecycle. SQLAlchemy async sessions are cheap.
    async for session in get_async_session():
        await session.execute(
            update(User).where(User.id == user.id).values(display_name=fetched)
        )
        await session.commit()
        break  # generator yields one session

    log.info(
        "set display_name=%r for user %s via %s OAuth",
        fetched, user.email, provider,
    )


async def _start_oauth(provider: str) -> dict:
    """Build the provider authorization URL with a signed CSRF state token."""
    client = _oauth_clients[provider]
    state = generate_state_token({}, settings.jwt_secret)
    url = await client.get_authorization_url(
        f"{settings.backend_url}/auth/{provider}/callback",
        state=state,
        scope=_oauth_scopes[provider],
    )
    return {"authorization_url": url}


async def _finish_oauth(provider, request, access_token_state, user_manager):
    """Exchange code, get/create user, populate name, set cookie, redirect."""
    token, state = access_token_state

    # Verify the state token (CSRF protection) - same check the built-in does.
    try:
        decode_jwt(state, settings.jwt_secret, [_OAUTH_STATE_AUDIENCE])
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid OAuth state token.")

    client = _oauth_clients[provider]
    account_id, account_email = await client.get_id_email(token["access_token"])

    if account_email is None:
        raise HTTPException(
            status_code=400,
            detail="OAuth provider did not return an email address.",
        )

    user = await user_manager.oauth_callback(
        provider,
        token["access_token"],
        account_id,
        account_email,
        token.get("expires_at"),
        token.get("refresh_token"),
        request,
        associate_by_email=True,
        is_verified_by_default=True,
    )

    # Populate display_name from provider on FIRST signup only. If the user
    # already has a name set (manual edit or a prior OAuth login that fetched
    # it), this is a no-op.
    await _maybe_set_display_name(user, provider, token["access_token"])

    # Suspended accounts: surface the same message OAuth users would see via
    # form login, by redirecting to login with an error query param so the
    # existing red banner can show it (a 403 here would just land on a blank
    # backend error page since this is a browser redirect flow).
    if not user.is_active:
        return RedirectResponse(
            url=(
                f"{settings.frontend_url}/login"
                "?error=Your%20account%20has%20been%20suspended."
                "%20Check%20your%20email%20for%20details."
            ),
            status_code=302,
        )

    # Issue the auth cookie via the cookie backend's strategy, attached to a
    # redirect to the frontend. Cookie attributes are read from the transport
    # so they match POST /auth/cookie/login exactly.
    redirect = RedirectResponse(url=f"{settings.frontend_url}/chat", status_code=302)
    strategy = cookie_backend.get_strategy()
    auth_token = await strategy.write_token(user)

    transport = cookie_backend.transport
    redirect.set_cookie(
        key=transport.cookie_name,
        value=auth_token,
        max_age=transport.cookie_max_age,
        path=transport.cookie_path,
        domain=transport.cookie_domain,
        secure=transport.cookie_secure,
        httponly=transport.cookie_httponly,
        samesite=transport.cookie_samesite,
    )
    return redirect


_OAUTH_LIMIT = [Depends(RateLimiter(times=20, seconds=60, scope="oauth"))]


# --- Google ---

@app.get("/auth/google/authorize", tags=["auth"], dependencies=_OAUTH_LIMIT)
async def google_authorize() -> dict:
    return await _start_oauth("google")


@app.get("/auth/google/callback", tags=["auth"], dependencies=_OAUTH_LIMIT)
async def google_callback(
    request: Request,
    access_token_state=Depends(_oauth_callbacks["google"]),
    user_manager=Depends(get_user_manager),
):
    return await _finish_oauth("google", request, access_token_state, user_manager)


# --- GitHub ---

@app.get("/auth/github/authorize", tags=["auth"], dependencies=_OAUTH_LIMIT)
async def github_authorize() -> dict:
    return await _start_oauth("github")


@app.get("/auth/github/callback", tags=["auth"], dependencies=_OAUTH_LIMIT)
async def github_callback(
    request: Request,
    access_token_state=Depends(_oauth_callbacks["github"]),
    user_manager=Depends(get_user_manager),
):
    return await _finish_oauth("github", request, access_token_state, user_manager)


# --- User management routes --------------------------------------------------
# fastapi-users' own dependencies on these routes skip the force-logout
# freshness check, so a revoked token could still read/patch /users/me
# (incl. changing the password). The router-level current_active_user closes
# that gap for every /users route.
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
    dependencies=[
        Depends(current_active_user),
        Depends(RateLimiter(times=60, seconds=60, scope="users")),
    ],
)


@app.get("/health")
def health():
    """Public health check."""
    return {
        "status": "ok",
        "version": __version__,
        "provider": active_provider(),
        "model": active_model_name(),
        "embedding_model": settings.embedding_model,
        "voice_enabled": settings.enable_voice,
        "tts_backend": settings.tts_backend,
        "indexed": None,
    }


@app.get("/")
def root():
    return {
        "name": "GenAI Agent",
        "version": __version__,
        "docs": "/docs",
        "endpoints": {
            "health": "/health",
            "register": "POST /auth/register",
            "login_bearer": "POST /auth/jwt/login (for API/curl, returns token JSON)",
            "login_cookie": "POST /auth/cookie/login (for browser, sets httpOnly cookie)",
            "logout_cookie": "POST /auth/cookie/logout",
            "oauth_google": "GET /auth/google/authorize",
            "oauth_github": "GET /auth/github/authorize",
            "me": "GET /users/me",
            "documents": "GET/POST/DELETE /rag/documents",
            "rag_query": "POST /rag/query",
            "agent_chat": "POST /agent/chat",
            "agent_stream": "POST /agent/stream",
            "transcribe": "POST /voice/transcribe",
            "tts": "POST /voice/tts",
        },
    }