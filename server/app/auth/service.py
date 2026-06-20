"""Session lifecycle: issue, refresh (with rotation + reuse-revocation), revoke.

This is the DB-backed half of auth (the pure crypto is in :mod:`.tokens`). A
refresh token belongs to a *family*; rotating it revokes the old one and issues a
successor in the same family. Presenting an already-rotated (revoked) token is
treated as theft: the **entire family is revoked**, logging every session derived
from it out. Standard refresh-token reuse detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg

from .. import repositories as repo
from ..config import Settings
from .tokens import (
    AuthError,
    generate_refresh_token,
    hash_refresh_token,
    mint_access_token,
)


@dataclass(frozen=True)
class SessionTokens:
    """What a successful login/refresh hands back to the client."""

    access_token: str
    refresh_token: str
    user_id: str
    display_name: str
    primary_email: str | None


class AuthService:
    """Mints and rotates session tokens against the database."""

    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None:
        self._pool = pool
        self._settings = settings

    async def dev_login(self, *, email: str, display_name: str | None) -> SessionTokens:
        """Local-only login: get-or-create a user by email and issue tokens.

        Guarded by the caller to non-production. No password — this is the
        stand-in for real OIDC sign-in so the stack is runnable end to end.
        """
        async with self._pool.acquire() as conn, conn.transaction():
            user = await repo.get_or_create_user_by_email(
                conn, email=email, display_name=display_name
            )
            return await self._issue(conn, user, family_id=str(uuid4()))

    async def refresh(self, raw_refresh: str) -> SessionTokens:
        """Rotate a refresh token. Reuse of a revoked token kills the family.

        The reuse-revocation must **commit** before we raise, so it is done outside
        the rotation transaction — raising inside a transaction would roll the
        revocation back, defeating the whole reuse-detection mechanism.
        """
        token_hash = hash_refresh_token(raw_refresh)
        async with self._pool.acquire() as conn:
            record = await repo.get_refresh_token(conn, token_hash)
            if record is None:
                raise AuthError("unknown refresh token")
            if record["revoked"]:
                # Reuse of an already-rotated token → revoke the whole family (commits
                # immediately; no enclosing transaction to roll it back).
                await repo.revoke_refresh_family(conn, record["family_id"])
                raise AuthError("refresh token reuse detected")
            if record["expires_at"] < datetime.now(UTC):
                raise AuthError("refresh token expired")

            user = await repo.get_user(conn, record["user_id"])
            if user is None:
                raise AuthError("user no longer exists")
            # Atomically retire the old token and issue its successor in the family.
            async with conn.transaction():
                await repo.revoke_refresh_token(conn, token_hash)
                return await self._issue(conn, user, family_id=str(record["family_id"]))

    async def logout(self, raw_refresh: str) -> None:
        """Revoke the presented token's whole family (idempotent)."""
        token_hash = hash_refresh_token(raw_refresh)
        async with self._pool.acquire() as conn:
            record = await repo.get_refresh_token(conn, token_hash)
            if record is not None:
                await repo.revoke_refresh_family(conn, record["family_id"])

    async def _issue(
        self, conn: asyncpg.Connection, user: dict, *, family_id: str
    ) -> SessionTokens:
        user_id = str(user["id"])
        display_name = user.get("display_name") or ""
        access = mint_access_token(
            user_id=user_id,
            display_name=display_name,
            secret=self._settings.JWT_SECRET,
            ttl_seconds=self._settings.JWT_ACCESS_TTL_SECONDS,
        )
        raw_refresh, token_hash = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(seconds=self._settings.JWT_REFRESH_TTL_SECONDS)
        await repo.insert_refresh_token(
            conn,
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        return SessionTokens(
            access_token=access,
            refresh_token=raw_refresh,
            user_id=user_id,
            display_name=display_name,
            primary_email=user.get("primary_email"),
        )
