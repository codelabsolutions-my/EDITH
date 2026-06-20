"""Integration tests for the DB-backed auth session service.

Covers the critical auth paths called out in engineering.md: JWT issue, refresh
rotation, and reuse-revocation. Skips when the test Postgres is unreachable.
"""

from __future__ import annotations

import asyncio

import asyncpg
import pytest
from app.auth.service import AuthService
from app.auth.tokens import AuthError, verify_access_token
from app.config import get_settings
from tests.conftest import reset_db


async def _service(dsn: str) -> tuple[AuthService, asyncpg.Pool]:
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    assert pool is not None
    await reset_db(pool)
    return AuthService(pool, get_settings()), pool


def test_dev_login_issues_verifiable_access_token(pg_dsn: str) -> None:
    async def scenario() -> None:
        service, pool = await _service(pg_dsn)
        try:
            tokens = await service.dev_login(email="ali@example.com", display_name="Ali")
            user = verify_access_token(tokens.access_token, secret=get_settings().JWT_SECRET)
            assert user.id == tokens.user_id
            assert user.display_name == "Ali"
            # The refresh token is stored only as a hash.
            row = await pool.fetchrow(
                "SELECT token_hash FROM refresh_tokens WHERE user_id = $1", user.id
            )
            assert row is not None and row["token_hash"] != tokens.refresh_token
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_dev_login_is_idempotent_per_email(pg_dsn: str) -> None:
    async def scenario() -> None:
        service, pool = await _service(pg_dsn)
        try:
            a = await service.dev_login(email="same@example.com", display_name="A")
            b = await service.dev_login(email="SAME@example.com", display_name="A")
            assert a.user_id == b.user_id  # case-insensitive email match
            count = await pool.fetchval("SELECT count(*) FROM users")
            assert count == 1
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_refresh_rotates_and_old_token_stops_working(pg_dsn: str) -> None:
    async def scenario() -> None:
        service, pool = await _service(pg_dsn)
        try:
            first = await service.dev_login(email="rot@example.com", display_name="R")
            second = await service.refresh(first.refresh_token)
            assert second.refresh_token != first.refresh_token
            # The rotated-away token is now revoked: reusing it fails.
            with pytest.raises(AuthError):
                await service.refresh(first.refresh_token)
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_reuse_of_revoked_token_revokes_whole_family(pg_dsn: str) -> None:
    async def scenario() -> None:
        service, pool = await _service(pg_dsn)
        try:
            first = await service.dev_login(email="reuse@example.com", display_name="R")
            second = await service.refresh(first.refresh_token)  # rotate once
            # Replay the old (revoked) token: theft signal -> kill the family.
            with pytest.raises(AuthError):
                await service.refresh(first.refresh_token)
            # The currently-valid successor is now also revoked.
            with pytest.raises(AuthError):
                await service.refresh(second.refresh_token)
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_logout_revokes_family(pg_dsn: str) -> None:
    async def scenario() -> None:
        service, pool = await _service(pg_dsn)
        try:
            tokens = await service.dev_login(email="out@example.com", display_name="O")
            await service.logout(tokens.refresh_token)
            with pytest.raises(AuthError):
                await service.refresh(tokens.refresh_token)
        finally:
            await pool.close()

    asyncio.run(scenario())
