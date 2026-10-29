"""Check that an OAuth provider has verified the account's email address.

httpx-oauth's get_id_email() returns an address without saying whether the
provider verified it (its GitHub client can even fall back to an unverified
address). Linking an OAuth login to an existing account by email is only safe
for verified addresses; otherwise anyone could add a victim's address to
their provider account and sign in as the victim.

Any failure (network, unexpected payload) counts as "not verified".
"""
from typing import Any

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


async def _get_json(url: str, headers: dict, transport: httpx.AsyncBaseTransport | None) -> Any:
    async with httpx.AsyncClient(timeout=5.0, transport=transport) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def provider_email_verified(
    provider: str,
    access_token: str,
    email: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """True only if `provider` reports `email` as verified for this token."""
    wanted = (email or "").strip().lower()
    if not wanted:
        return False
    try:
        if provider == "google":
            data = await _get_json(
                GOOGLE_USERINFO_URL, {"Authorization": f"Bearer {access_token}"}, transport
            )
            return (
                str(data.get("email", "")).lower() == wanted
                and data.get("email_verified") is True
            )
        if provider == "github":
            emails = await _get_json(
                GITHUB_EMAILS_URL,
                {
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                transport,
            )
            return any(
                str(e.get("email", "")).lower() == wanted and e.get("verified") is True
                for e in emails
            )
    except Exception as e:
        log.warning("could not confirm %s email verification: %s", provider, e)
    return False
