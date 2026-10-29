"""fastapi-users wiring: user manager, dual auth backends, OAuth clients.

Backends:
  - "jwt": Bearer token transport (API/curl/mobile)
  - "cookie": httpOnly cookie transport (web frontend)
Both share one JWT strategy. OAuth (Google + GitHub) issues the same cookie.

Force-logout enforcement (security-critical):
  - Our JWT strategy adds an `iat` (issued-at) claim to every token.
  - When an admin force-logs out a user, users.jwt_invalidated_at is set.
  - Every request that depends on `current_active_user` runs the freshness
    check: if the JWT's iat predates jwt_invalidated_at, 401.
  - This means force-logout is genuinely global: chat, RAG, sessions, admin -
    every authenticated endpoint rejects stale tokens on the very next call.

Account suspension at login:
  - UserManager.authenticate is overridden so that when the password is
    correct but is_active=False, we raise AccountSuspendedError instead of
    returning None. main.py registers an exception handler that turns this
    into a 403 with a clear message. Wrong-password and unknown-user still
    return None (generic "bad credentials") so attackers can't probe whether
    a given email is suspended vs nonexistent.
"""
import uuid
from datetime import datetime, timezone

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.jwt import generate_jwt
from httpx_oauth.clients.github import GitHubOAuth2
from httpx_oauth.clients.google import GoogleOAuth2
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_event
from app.core.config import settings
from app.core.db import get_async_session
from app.core.email import (
    password_changed_email,
    password_reset_email,
    send_email,
)
from app.core.logging import get_logger
from app.core.rate_limit import keyed_count, keyed_hit
from app.core.roles import UserRole
from app.models.user import OAuthAccount, User

log = get_logger(__name__)

# Per-account / per-address throttles (on top of the per-IP router limits), so
# attackers spread over many IPs cannot brute-force one account or flood one
# inbox. Keyed by the submitted email (hashed), including unknown emails, so
# behaviour does not reveal which accounts exist.
LOGIN_FAILURE_LIMIT = 10
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
EMAILS_PER_ADDRESS_LIMIT = 3
EMAILS_PER_ADDRESS_WINDOW_SECONDS = 60 * 60


# --- Custom auth exception ----------------------------------------------------
# Raised by UserManager.authenticate when the password is correct but the
# user has been suspended (is_active=False). main.py registers an exception
# handler that turns this into a 403 with a clear message.

class AccountSuspendedError(Exception):
    """Raised when a user with correct credentials is blocked / suspended.

    Carries an optional `email` for logging at the handler. We deliberately
    do NOT include the admin-set reason here; the reason lives in the email
    sent at block time. The login response is intentionally generic to avoid
    leaking admin notes through the API.
    """
    def __init__(self, email: str = ""):
        super().__init__("Account suspended")
        self.email = email


# --- User database adapter (now with OAuth support) ---

async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


# --- User manager ---

# Server-side password policy. The frontend checks the minimum too, but the
# API must enforce it for direct API clients. The maximum bounds the cost of
# hashing attacker-supplied input.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret

    async def validate_password(self, password: str, user) -> None:
        """Reject weak passwords on register, update and reset.

        fastapi-users calls this from create(), update() and reset_password();
        raising InvalidPasswordException becomes a 400 with code
        REGISTER_/UPDATE_USER_/RESET_PASSWORD_INVALID_PASSWORD.
        """
        from fastapi_users.exceptions import InvalidPasswordException

        if len(password) < PASSWORD_MIN_LENGTH:
            raise InvalidPasswordException(
                reason=f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
            )
        if len(password) > PASSWORD_MAX_LENGTH:
            raise InvalidPasswordException(
                reason=f"Password must be at most {PASSWORD_MAX_LENGTH} characters."
            )
        if not password.strip():
            raise InvalidPasswordException(reason="Password cannot be only whitespace.")
        email = (getattr(user, "email", "") or "").lower()
        local_part = email.split("@")[0]
        lowered = password.lower()
        if email and (email in lowered or (len(local_part) >= 3 and local_part in lowered)):
            raise InvalidPasswordException(
                reason="Password must not contain your email address."
            )

    async def _sync_superuser_flag(self, user: User) -> None:
        """Mirror is_superuser from role (super_admin <-> is_superuser=True).

        role is the source of truth; this keeps fastapi-users' built-in
        superuser checks consistent with it.
        """
        should_be = (
            getattr(user, "role", UserRole.user.value) == UserRole.super_admin.value
        )
        if user.is_superuser != should_be:
            await self.user_db.update(user, {"is_superuser": should_be})

    async def authenticate(
        self, credentials: OAuth2PasswordRequestForm
    ) -> User | None:
        """Override fastapi-users authenticate to detect suspended accounts.

        Behavior:
          - User not found / wrong password -> return None (generic bad creds).
          - Correct password + is_active=False -> raise AccountSuspendedError.
          - Correct password + active -> return user (normal flow).

        This means probing emails with wrong passwords always gets the same
        generic response; only someone with the correct password learns that
        an account is suspended. Acceptable tradeoff: the legit user finds
        out exactly when they need to, attackers gain nothing.
        """
        # Same shape as fastapi-users' default implementation, adapted to
        # raise on inactive-but-correct-password.
        from fastapi_users import exceptions as fu_exceptions

        # Per-account lockout: once an email has too many recent failures,
        # refuse every attempt (even a correct password) until the window
        # ends, so distributed guessing cannot continue.
        account = credentials.username
        failures = await keyed_count("login_fail", account, LOGIN_FAILURE_WINDOW_SECONDS)
        if failures >= LOGIN_FAILURE_LIMIT:
            audit_event("login", actor=account, status="blocked",
                        reason="too_many_failures")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Try again later.",
                headers={"Retry-After": str(LOGIN_FAILURE_WINDOW_SECONDS)},
            )

        try:
            user = await self.get_by_email(account)
        except fu_exceptions.UserNotExists:
            # Run the hasher to mitigate timing attack (mirrors upstream).
            self.password_helper.hash(credentials.password)
            await keyed_hit("login_fail", account, LOGIN_FAILURE_WINDOW_SECONDS)
            return None

        verified, updated_password_hash = self.password_helper.verify_and_update(
            credentials.password, user.hashed_password
        )
        if not verified:
            audit_event("login", actor=account, status="failure",
                        reason="bad_password")
            await keyed_hit("login_fail", account, LOGIN_FAILURE_WINDOW_SECONDS)
            return None
        if updated_password_hash is not None:
            await self.user_db.update(user, {"hashed_password": updated_password_hash})

        # Password is correct. If the account is suspended, surface that
        # specifically instead of letting the router return generic bad creds.
        if not user.is_active:
            log.info("blocked-user login attempt: %s", user.email)
            audit_event("login", actor=user.email, status="blocked",
                        reason="suspended")
            raise AccountSuspendedError(email=user.email)

        return user

    async def on_after_register(self, user: User, request=None):
        log.info("user registered: %s (%s)", user.email, user.id)
        audit_event("register", actor=user.email, target=str(user.id))
        await self._sync_superuser_flag(user)
        # Kick off email verification for password signups. Guarded so it's a
        # no-op for already-verified users (OAuth signups set is_verified=True)
        # and best-effort so a missing/broken SMTP config never fails the
        # registration itself — the user is created either way and can request
        # a fresh verification link later.
        if not user.is_verified:
            try:
                await self.request_verify(user, request)
            except Exception as e:
                log.warning(
                    "could not send verification email for %s: %s", user.email, e
                )

    async def _invalidate_existing_tokens(self, user: User) -> None:
        """Revoke every JWT issued before now (same mechanism as force-logout).

        Used after a password change/reset so a stolen session token stops
        working; the user simply logs in again with the new password.
        """
        await self.user_db.update(
            user, {"jwt_invalidated_at": datetime.now(timezone.utc)}
        )

    async def update(self, user_update, user: User, safe: bool = False, request=None):
        """Require the current password for self-service credential changes.

        safe=True is the PATCH /users/me path. Changing the password, or the
        email to a different address, needs `current_password`, so a stolen
        session token alone cannot take over the account. Superuser updates
        (safe=False) and display-name-only changes are unaffected. Accounts
        created via OAuth have no known password; they can set one through the
        forgot-password flow first.
        """
        from fastapi_users.exceptions import InvalidPasswordException

        changes_password = getattr(user_update, "password", None) is not None
        new_email = getattr(user_update, "email", None)
        changes_email = new_email is not None and str(new_email).lower() != user.email.lower()
        if safe and (changes_password or changes_email):
            current = getattr(user_update, "current_password", None) or ""
            verified, _ = self.password_helper.verify_and_update(current, user.hashed_password)
            if not verified:
                audit_event("credentials.change", actor=user.email, status="failure",
                            reason="bad_current_password")
                raise InvalidPasswordException(reason="Current password is incorrect.")

        # current_password is request-only: never pass it on to the update.
        if "current_password" in user_update.model_fields_set:
            user_update = type(user_update)(
                **user_update.model_dump(exclude_unset=True, exclude={"current_password"})
            )
        return await super().update(user_update, user, safe=safe, request=request)

    async def on_after_update(self, user: User, update_dict: dict, request=None):
        # If an admin changed the user's role, keep is_superuser consistent.
        if "role" in update_dict:
            await self._sync_superuser_flag(user)
        if update_dict.get("password"):
            log.info("password updated for %s; revoking existing sessions", user.email)
            audit_event("password.change", actor=user.email)
            await self._invalidate_existing_tokens(user)

    async def _email_quota_exceeded(self, kind: str, email: str) -> bool:
        """Count one outgoing `kind` email to `email`; True if over the limit.

        The API still answers 202 when the quota is hit (no enumeration); the
        email is just not sent, so one inbox cannot be flooded.
        """
        sent = await keyed_hit(f"{kind}_email", email, EMAILS_PER_ADDRESS_WINDOW_SECONDS)
        if sent > EMAILS_PER_ADDRESS_LIMIT:
            log.warning("%s email to %s suppressed (per-address limit)", kind, email)
            audit_event(f"{kind}.email", actor=email, status="blocked",
                        reason="per_address_limit")
            return True
        return False

    async def on_after_forgot_password(self, user: User, token: str, request=None):
        log.info("password reset requested for %s", user.email)
        audit_event("password.forgot", actor=user.email)
        if await self._email_quota_exceeded("reset", user.email):
            return
        reset_link = f"{settings.frontend_url}/reset-password?token={token}"
        subject, html_body, text_body = password_reset_email(reset_link)
        await send_email(user.email, subject, html_body, text_body)

    async def on_after_request_verify(self, user: User, token: str, request=None):
        log.info("email verification requested for %s", user.email)
        audit_event("verify.request", actor=user.email)
        if await self._email_quota_exceeded("verify", user.email):
            return
        verify_link = f"{settings.frontend_url}/verify-email?token={token}"
        subject = "Verify your CloudNest email"
        html_body = (
            "<p>Welcome to CloudNest! Please confirm your email address by "
            f'clicking the link below:</p><p><a href="{verify_link}">Verify my '
            "email</a></p><p>If you didn't create this account, you can ignore "
            "this message.</p>"
        )
        text_body = (
            "Welcome to CloudNest! Confirm your email address by opening this "
            f"link:\n{verify_link}\n\nIf you didn't create this account, ignore "
            "this message."
        )
        # Best-effort: don't let an SMTP failure bubble up and break the
        # register/request-verify request.
        try:
            await send_email(user.email, subject, html_body, text_body)
        except Exception as e:
            log.warning("verification email send failed for %s: %s", user.email, e)

    async def on_after_verify(self, user: User, request=None):
        log.info("email verified for %s", user.email)
        audit_event("verify.success", actor=user.email)

    async def on_after_login(self, user: User, request=None, response=None):
        log.info("user logged in: %s (%s)", user.email, user.id)
        audit_event("login", actor=user.email, status="success")

    async def on_after_reset_password(self, user: User, request=None):
        log.info("password changed for %s", user.email)
        audit_event("password.reset", actor=user.email)
        await self._invalidate_existing_tokens(user)
        when = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
        subject, html_body, text_body = password_changed_email(when)
        await send_email(user.email, subject, html_body, text_body)


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)


# --- JWT strategy WITH iat claim ----------------------------------------------
# fastapi-users' default JWTStrategy emits only {sub, aud, exp}. We need `iat`
# so we can detect tokens issued before a user was force-logged-out.

class JWTStrategyWithIat(JWTStrategy):
    async def write_token(self, user) -> str:
        data = {
            "sub": str(user.id),
            "aud": self.token_audience,
            "iat": int(datetime.now(timezone.utc).timestamp()),
        }
        return generate_jwt(
            data, self.encode_key, self.lifetime_seconds, algorithm=self.algorithm
        )


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategyWithIat(
        secret=settings.jwt_secret,
        lifetime_seconds=settings.jwt_lifetime_seconds,
    )


# --- Backend 1: Bearer (API/curl/mobile) ---

bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")

jwt_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)


# --- Backend 2: Cookie (web frontend) ---

# Secure cookie flag, env-driven. Defaults to False for local http dev; set
# COOKIE_SECURE=true in production (over HTTPS) so the cookie is only sent on
# secure connections. NOTE: if the frontend and API are on DIFFERENT domains in
# production, the browser won't send a SameSite=lax cookie on cross-site
# requests — you'd need samesite="none" (which REQUIRES secure=True). Keep them
# same-site (e.g. app.example.com + api.example.com share example.com) to stay
# on the safer "lax".
_COOKIE_SECURE = settings.COOKIE_SECURE

cookie_transport = CookieTransport(
    cookie_name="genai_auth",
    cookie_max_age=settings.jwt_lifetime_seconds,
    cookie_httponly=True,
    cookie_secure=_COOKIE_SECURE,
    cookie_samesite="lax",
)

cookie_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)


# --- OAuth clients ---

google_oauth_client = GoogleOAuth2(
    settings.google_oauth_client_id,
    settings.google_oauth_client_secret,
)

github_oauth_client = GitHubOAuth2(
    settings.github_oauth_client_id,
    settings.github_oauth_client_secret,
)


# --- The fastapi-users instance ---

fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [cookie_backend, jwt_backend],
)

# fastapi-users' raw dependency (signature + active check only, NO freshness
# check). Used internally by the freshness check below. NOT exported as the
# default `current_active_user` because force-logout needs to be global.
_current_active_user_no_freshness = fastapi_users.current_user(active=True)


# --- Freshness check: rejects JWTs issued before force-logout -----------------

def _extract_token(request: Request) -> str | None:
    """Pull a JWT from either the Bearer header or the cookie."""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.cookies.get("genai_auth")


async def _check_freshness(request: Request, user: User) -> User:
    """Reject the request if the JWT was issued before force-logout.

    If users.jwt_invalidated_at is set and the JWT's iat is earlier (or the
    token has no iat at all -- pre-upgrade tokens), the request is rejected
    with 401. The user can simply log in again to get a fresh token.
    """
    invalidated = getattr(user, "jwt_invalidated_at", None)
    if invalidated is None:
        return user  # never force-logged-out, nothing to check

    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
        )

    try:
        payload = pyjwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience="fastapi-users:auth",
            options={"verify_signature": True, "verify_exp": True},
        )
    except pyjwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
        ) from None

    iat = payload.get("iat")
    if iat is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired, please log in again",
        )

    if iat < int(invalidated.timestamp()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session was force-logged-out by an admin",
        )

    return user


async def current_active_user(
    request: Request,
    user: User = Depends(_current_active_user_no_freshness),
) -> User:
    """Active user + JWT-freshness check (rejects force-logged-out tokens).

    This is the dependency every authenticated route should use. Combines:
      1. fastapi-users active-user check (signature, expiry, is_active)
      2. iat-cutoff check against users.jwt_invalidated_at
    """
    return await _check_freshness(request, user)


# Backward-compat alias. `current_active_fresh_user` was the name used by
# app/core/admin_deps.py before force-logout went global. Keep the alias so
# existing admin_deps imports stay working without edits.
current_active_fresh_user = current_active_user


# Backwards-compat alias.
auth_backend = jwt_backend
