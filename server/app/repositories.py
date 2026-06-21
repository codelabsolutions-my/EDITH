"""Data access over asyncpg — plain SQL, no ORM (per the locked architecture).

Functions here take a connection or pool and own one query each. They are the
only place SQL lives outside migrations; higher layers (auth service, session
persistence) compose them. Everything is keyed by ``user_id`` — multi-tenant from
day one, no global state.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

# ─── users ──────────────────────────────────────────────────────────────────


async def get_or_create_user_by_email(
    conn: asyncpg.Connection, *, email: str, display_name: str | None
) -> dict[str, Any]:
    """Return the user with this email, creating one if absent.

    Email match is case-insensitive (the unique index is on ``lower(email)``).
    """
    row = await conn.fetchrow("SELECT * FROM users WHERE lower(primary_email) = lower($1)", email)
    if row is not None:
        return dict(row)
    row = await conn.fetchrow(
        """
        INSERT INTO users (display_name, primary_email)
        VALUES ($1, $2)
        RETURNING *
        """,
        display_name,
        email,
    )
    assert row is not None
    return dict(row)


async def get_user(conn: asyncpg.Connection, user_id: UUID | str) -> dict[str, Any] | None:
    row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", _as_uuid(user_id))
    return dict(row) if row else None


# ─── provider_accounts (OAuth API grants) ───────────────────────────────────


async def upsert_provider_account(
    conn: asyncpg.Connection,
    *,
    user_id: UUID | str,
    provider: str,
    provider_subject: str,
    email: str | None,
    scopes: str | None,
    access_token_enc: bytes | None,
    refresh_token_enc: bytes | None,
    token_expiry: datetime | None,
) -> None:
    """Store/refresh a user's OAuth grant for a provider (encrypted tokens).

    Keeps the existing refresh token when a refresh response omits one (Google only
    returns it on first consent).
    """
    await conn.execute(
        """
        INSERT INTO provider_accounts (
            user_id, provider, provider_subject, email, scopes,
            access_token_enc, refresh_token_enc, token_expiry
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (user_id, provider) DO UPDATE SET
            provider_subject = EXCLUDED.provider_subject,
            email = EXCLUDED.email,
            scopes = EXCLUDED.scopes,
            access_token_enc = EXCLUDED.access_token_enc,
            refresh_token_enc = COALESCE(EXCLUDED.refresh_token_enc, provider_accounts.refresh_token_enc),
            token_expiry = EXCLUDED.token_expiry
        """,
        _as_uuid(user_id),
        provider,
        provider_subject,
        email,
        scopes,
        access_token_enc,
        refresh_token_enc,
        token_expiry,
    )


async def get_provider_account(
    conn: asyncpg.Connection, *, user_id: UUID | str, provider: str
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        "SELECT * FROM provider_accounts WHERE user_id = $1 AND provider = $2",
        _as_uuid(user_id),
        provider,
    )
    return dict(row) if row else None


# ─── refresh_tokens ─────────────────────────────────────────────────────────


async def insert_refresh_token(
    conn: asyncpg.Connection,
    *,
    user_id: UUID | str,
    family_id: UUID | str,
    token_hash: str,
    expires_at: datetime,
) -> None:
    await conn.execute(
        """
        INSERT INTO refresh_tokens (user_id, family_id, token_hash, expires_at)
        VALUES ($1, $2, $3, $4)
        """,
        _as_uuid(user_id),
        _as_uuid(family_id),
        token_hash,
        expires_at,
    )


async def get_refresh_token(conn: asyncpg.Connection, token_hash: str) -> dict[str, Any] | None:
    row = await conn.fetchrow("SELECT * FROM refresh_tokens WHERE token_hash = $1", token_hash)
    return dict(row) if row else None


async def revoke_refresh_token(conn: asyncpg.Connection, token_hash: str) -> None:
    await conn.execute("UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = $1", token_hash)


async def revoke_refresh_family(conn: asyncpg.Connection, family_id: UUID | str) -> None:
    """Revoke every token in a family — the reuse-detection hammer."""
    await conn.execute(
        "UPDATE refresh_tokens SET revoked = TRUE WHERE family_id = $1", _as_uuid(family_id)
    )


# ─── conversations + messages ───────────────────────────────────────────────


async def create_conversation(conn: asyncpg.Connection, *, user_id: UUID | str) -> UUID:
    row = await conn.fetchrow(
        "INSERT INTO conversations (user_id) VALUES ($1) RETURNING id", _as_uuid(user_id)
    )
    assert row is not None
    return row["id"]  # type: ignore[no-any-return]


async def end_conversation(conn: asyncpg.Connection, conversation_id: UUID | str) -> None:
    await conn.execute(
        "UPDATE conversations SET ended_at = now() WHERE id = $1 AND ended_at IS NULL",
        _as_uuid(conversation_id),
    )


async def insert_message(
    conn: asyncpg.Connection,
    *,
    conversation_id: UUID | str,
    user_id: UUID | str,
    role: str,
    content: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO messages (conversation_id, user_id, role, content)
        VALUES ($1, $2, $3, $4)
        """,
        _as_uuid(conversation_id),
        _as_uuid(user_id),
        role,
        content,
    )


# ─── action_log ─────────────────────────────────────────────────────────────


async def insert_action(
    conn: asyncpg.Connection,
    *,
    user_id: UUID | str,
    tool: str,
    args_summary: str,
    result_summary: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO action_log (user_id, tool, args_summary, result)
        VALUES ($1, $2, $3, $4)
        """,
        _as_uuid(user_id),
        tool,
        args_summary,
        result_summary,
    )


# ─── usage_log ──────────────────────────────────────────────────────────────


async def insert_usage(
    conn: asyncpg.Connection,
    *,
    user_id: UUID | str,
    call_type: str,
    voice_seconds: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    await conn.execute(
        """
        INSERT INTO usage_log (user_id, call_type, voice_seconds, input_tokens, output_tokens)
        VALUES ($1, $2, $3, $4, $5)
        """,
        _as_uuid(user_id),
        call_type,
        Decimal(str(round(voice_seconds, 3))),  # NUMERIC(10,3) wants a Decimal
        input_tokens,
        output_tokens,
    )


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))
