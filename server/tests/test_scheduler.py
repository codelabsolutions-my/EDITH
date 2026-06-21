"""ProactiveScheduler: delivers due reminders, marks them, leaves future ones."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg
from app.proactivity.push import DeviceTarget, Notification, PushSender
from app.proactivity.scheduler import ProactiveScheduler
from tests.conftest import reset_db


class RecordingPush(PushSender):
    def __init__(self) -> None:
        self.sent: list[tuple[list[DeviceTarget], Notification]] = []

    async def send(self, targets: list[DeviceTarget], notification: Notification) -> int:
        self.sent.append((targets, notification))
        return len(targets)


async def _make_user(pool: asyncpg.Pool) -> str:
    return str(
        await pool.fetchval("INSERT INTO users (primary_email) VALUES ('r@x.com') RETURNING id")
    )


def test_run_once_delivers_due_and_skips_future(pg_dsn: str) -> None:
    async def scenario() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=3)
        assert pool is not None
        try:
            await reset_db(pool)
            uid = await _make_user(pool)
            await pool.execute(
                "INSERT INTO device_tokens (user_id, platform, token) VALUES ($1,'fcm','dev-1')",
                uid,
            )
            now = datetime.now(UTC)
            await pool.execute(
                "INSERT INTO reminders (user_id, text, remind_at) VALUES ($1,'past due',$2)",
                uid,
                now - timedelta(minutes=5),
            )
            await pool.execute(
                "INSERT INTO reminders (user_id, text, remind_at) VALUES ($1,'future',$2)",
                uid,
                now + timedelta(hours=1),
            )

            push = RecordingPush()
            sched = ProactiveScheduler(pool, push)
            delivered = await sched.run_once(now=now)

            assert delivered == 1
            assert len(push.sent) == 1
            targets, note = push.sent[0]
            assert note.body == "past due"
            assert targets[0].token == "dev-1"

            # Marked delivered → a second tick delivers nothing; future stays pending.
            assert await sched.run_once(now=now) == 0
            pending = await pool.fetchval(
                "SELECT count(*) FROM reminders WHERE user_id=$1 AND NOT delivered", uid
            )
            assert pending == 1  # the future one
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_delivery_marks_even_without_devices(pg_dsn: str) -> None:
    """A reminder with no registered device is still marked, so it won't loop forever."""

    async def scenario() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=3)
        assert pool is not None
        try:
            await reset_db(pool)
            uid = await _make_user(pool)
            now = datetime.now(UTC)
            await pool.execute(
                "INSERT INTO reminders (user_id, text, remind_at) VALUES ($1,'no device',$2)",
                uid,
                now - timedelta(minutes=1),
            )
            sched = ProactiveScheduler(pool, RecordingPush())
            assert await sched.run_once(now=now) == 1
            assert await sched.run_once(now=now) == 0
        finally:
            await pool.close()

    asyncio.run(scenario())
