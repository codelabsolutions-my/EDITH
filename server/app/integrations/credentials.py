"""Resolve per-user connector credentials from the encrypted token store.

At session start we build a ``{connector_key: credentials}`` map the agent's tool
catalog reads from. A single Google OAuth grant can cover several APIs (Gmail,
Calendar, …) via incremental scopes, so we resolve the access token once (decrypt,
refresh-if-expired, re-store) and hand it to whichever connectors the granted
scopes cover — connectors never touch crypto or refresh.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from .. import repositories as repo
from ..auth.crypto import TokenCryptoError, decrypt, encrypt, load_key
from ..config import Settings
from .google_oauth import (
    CALENDAR_READONLY_SCOPE,
    GMAIL_READONLY_SCOPE,
    GoogleOAuth,
    OAuthError,
)

log = logging.getLogger("edith.integrations")

# Refresh a little before actual expiry to avoid races mid-turn.
_EXPIRY_SKEW = timedelta(seconds=60)

# Which connector key gets the token for which granted scope.
_SCOPE_TO_CONNECTOR = {
    GMAIL_READONLY_SCOPE: ("gmail", "gmail_access_token"),
    CALENDAR_READONLY_SCOPE: ("calendar", "calendar_access_token"),
}


async def build_credentials(
    pool: asyncpg.Pool, settings: Settings, user_id: str
) -> dict[str, dict[str, Any]]:
    """Build the per-connector credentials map for ``user_id`` (best-effort)."""
    grant = await google_access_token(pool, settings, user_id)
    if grant is None:
        return {}
    token, scopes = grant
    creds: dict[str, dict[str, Any]] = {}
    for scope, (connector_key, cred_key) in _SCOPE_TO_CONNECTOR.items():
        if scope in scopes:
            creds[connector_key] = {cred_key: token}
    return creds


async def google_access_token(
    pool: asyncpg.Pool, settings: Settings, user_id: str
) -> tuple[str, str] | None:
    """Return ``(access_token, granted_scopes)`` for the user, refreshing if needed."""
    if not settings.GOOGLE_CLIENT_ID:
        return None
    async with pool.acquire() as conn:
        account = await repo.get_provider_account(conn, user_id=user_id, provider="google")
    if account is None or not account.get("access_token_enc"):
        return None
    scopes = account.get("scopes") or ""

    try:
        key = load_key(settings)
        expiry = account.get("token_expiry")
        if expiry is not None and expiry > datetime.now(UTC) + _EXPIRY_SKEW:
            return decrypt(bytes(account["access_token_enc"]), key), scopes
        # Expired (or no expiry recorded) → refresh if we can.
        if not account.get("refresh_token_enc"):
            return decrypt(bytes(account["access_token_enc"]), key), scopes  # best effort
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
                scopes=scopes,
                access_token_enc=encrypt(fresh.access_token, key),
                refresh_token_enc=None,  # keep the stored refresh token
                token_expiry=new_expiry,
            )
        return fresh.access_token, scopes
    except (TokenCryptoError, OAuthError):
        log.exception("could not resolve Google token", extra={"user_id": user_id})
        return None
