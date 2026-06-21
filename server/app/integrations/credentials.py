"""Resolve per-user connector credentials from the encrypted token store.

At session start we build a ``{connector_key: credentials}`` map the agent's tool
catalog reads from. For Gmail that means: load the user's Google OAuth grant, decrypt
the access token, refresh it if expired (re-storing the new one), and hand the
connector a ready-to-use bearer token — so connectors never touch crypto or refresh.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from .. import repositories as repo
from ..auth.crypto import TokenCryptoError, decrypt, encrypt, load_key
from ..config import Settings
from .google_oauth import GMAIL_READONLY_SCOPE, GoogleOAuth, OAuthError

log = logging.getLogger("edith.integrations")

# Refresh a little before actual expiry to avoid races mid-turn.
_EXPIRY_SKEW = timedelta(seconds=60)


async def build_credentials(
    pool: asyncpg.Pool, settings: Settings, user_id: str
) -> dict[str, dict[str, Any]]:
    """Build the per-connector credentials map for ``user_id`` (best-effort)."""
    creds: dict[str, dict[str, Any]] = {}
    token = await gmail_access_token(pool, settings, user_id)
    if token:
        creds["gmail"] = {"gmail_access_token": token}
    return creds


async def gmail_access_token(pool: asyncpg.Pool, settings: Settings, user_id: str) -> str | None:
    """Return a valid Gmail access token for the user, refreshing if needed."""
    if not settings.GOOGLE_CLIENT_ID:
        return None
    async with pool.acquire() as conn:
        account = await repo.get_provider_account(conn, user_id=user_id, provider="google")
    if account is None or GMAIL_READONLY_SCOPE not in (account.get("scopes") or ""):
        return None
    if not account.get("access_token_enc"):
        return None

    try:
        key = load_key(settings)
        expiry = account.get("token_expiry")
        if expiry is not None and expiry > datetime.now(UTC) + _EXPIRY_SKEW:
            return decrypt(bytes(account["access_token_enc"]), key)
        # Expired (or no expiry recorded) → refresh.
        if not account.get("refresh_token_enc"):
            return decrypt(bytes(account["access_token_enc"]), key)  # best effort
        refresh_token = decrypt(bytes(account["refresh_token_enc"]), key)
        oauth = GoogleOAuth(settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET)
        fresh = await oauth.refresh(refresh_token)
        new_expiry = datetime.now(UTC) + timedelta(seconds=fresh.expires_in)
        async with pool.acquire() as conn:
            await repo.upsert_provider_account(
                conn,
                user_id=user_id,
                provider="google",
                provider_subject=account["provider_subject"],
                email=account.get("email"),
                scopes=account.get("scopes"),
                access_token_enc=encrypt(fresh.access_token, key),
                refresh_token_enc=None,  # keep the stored refresh token
                token_expiry=new_expiry,
            )
        return fresh.access_token
    except (TokenCryptoError, OAuthError):
        log.exception("could not resolve Gmail token", extra={"user_id": user_id})
        return None
