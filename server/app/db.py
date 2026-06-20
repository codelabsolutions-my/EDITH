"""Database access: the asyncpg pool and the yoyo migration runner.

On startup the app applies migrations (``apply_migrations``) — a failure there
**blocks startup** — then opens an asyncpg pool (:class:`Database`). yoyo tracks
applied migrations in its own version table, so re-applying is a no-op.
"""

from __future__ import annotations

from pathlib import Path

import asyncpg
from yoyo import get_backend, read_migrations

from .logging_config import get_logger

log = get_logger("edith.db")

# server/migrations — sibling of the app package.
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def apply_migrations(database_url: str, *, migrations_dir: Path | None = None) -> int:
    """Apply all pending yoyo migrations. Returns the count applied.

    Raises on any migration error so the caller can block startup. yoyo uses a
    synchronous psycopg2 connection; this is fine at startup (one-shot).
    """
    path = migrations_dir or MIGRATIONS_DIR
    backend = get_backend(database_url)
    migrations = read_migrations(str(path))
    with backend.lock():
        to_apply = backend.to_apply(migrations)
        backend.apply_migrations(to_apply)
    count = len(list(to_apply))
    log.info("migrations applied", count=count, dir=str(path))
    return count


class Database:
    """A thin wrapper over an asyncpg connection pool."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool not connected — call connect() first")
        return self._pool

    async def connect(self, *, min_size: int = 1, max_size: int = 10) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=min_size, max_size=max_size)
            log.info("db pool connected")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            log.info("db pool closed")
