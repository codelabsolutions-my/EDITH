"""Reminder store — the DB-backed collaborator the reminders connector writes to.

Injected into the agent's tool context (like ``Memory``) so the ``set_reminder`` tool
can persist without the connector touching the pool directly. Absent (DB-less runs),
the tool reports reminders are unavailable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import asyncpg

from .. import repositories as repo


class ReminderStore:
    """Per-user reminder persistence."""

    def __init__(self, pool: asyncpg.Pool, user_id: str) -> None:
        self._pool = pool
        self._user_id = user_id

    async def add(self, text: str, remind_at: datetime) -> int:
        async with self._pool.acquire() as conn:
            return await repo.insert_reminder(
                conn, user_id=self._user_id, text=text, remind_at=remind_at
            )

    async def list(self) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            return await repo.list_reminders(conn, self._user_id)


def parse_remind_at(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; treat naive values as UTC. Raises ValueError."""
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
