"""Integration tests for PgMemory — tsvector recall + per-user isolation."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import asyncpg
from app.agent.memory import PgMemory
from tests.conftest import reset_db


async def _make_user(pool: asyncpg.Pool, email: str) -> str:
    row = await pool.fetchrow("INSERT INTO users (primary_email) VALUES ($1) RETURNING id", email)
    assert row is not None
    return str(row["id"])


def test_remember_then_recall_ranks_by_relevance(pg_dsn: str) -> None:
    async def scenario() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=4)
        assert pool is not None
        try:
            await reset_db(pool)
            user_id = await _make_user(pool, "mem@example.com")
            mem = PgMemory(pool)
            await mem.remember(user_id, "I park on level 3 at the office")
            await mem.remember(user_id, "My dog is named Rex")

            hits = await mem.recall(user_id, "where do I park")
            assert any("park on level 3" in h for h in hits)
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_recall_falls_back_to_recent_when_no_match(pg_dsn: str) -> None:
    async def scenario() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=4)
        assert pool is not None
        try:
            await reset_db(pool)
            user_id = await _make_user(pool, "fb@example.com")
            mem = PgMemory(pool)
            await mem.remember(user_id, "fact one")
            await mem.remember(user_id, "fact two")
            # A query that matches nothing still returns context (recent facts).
            hits = await mem.recall(user_id, "zzqqxx nonexistent")
            assert hits == ["fact one", "fact two"]
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_memory_is_isolated_per_user(pg_dsn: str) -> None:
    async def scenario() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=4)
        assert pool is not None
        try:
            await reset_db(pool)
            a = await _make_user(pool, "a@example.com")
            b = await _make_user(pool, "b@example.com")
            mem = PgMemory(pool)
            await mem.remember(a, "secret belonging to A")
            # User B recalls nothing of A's.
            assert await mem.recall(b, "secret") == []
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_unknown_user_recall_is_empty(pg_dsn: str) -> None:
    async def scenario() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=4)
        assert pool is not None
        try:
            await reset_db(pool)
            mem = PgMemory(pool)
            assert await mem.recall(str(uuid4()), "anything") == []
        finally:
            await pool.close()

    asyncio.run(scenario())
