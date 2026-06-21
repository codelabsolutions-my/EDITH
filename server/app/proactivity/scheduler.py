"""The proactive scheduler — polls for due work and pushes it to the user.

A single in-process asyncio loop (started in the app lifespan) ticks every
``poll_seconds``: it finds due, undelivered reminders, delivers each to the user's
registered devices via the :class:`~app.proactivity.push.PushSender`, and marks it
delivered. ``run_once`` exposes one tick for tests.

In-process is right at this scale; a multi-instance deployment would move this to a
durable queue / leader, but the seam (``run_once``) wouldn't change.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import asyncpg

from .. import repositories as repo
from .push import DeviceTarget, Notification, PushSender

log = logging.getLogger("edith.scheduler")


class ProactiveScheduler:
    """Background loop delivering due reminders as push notifications."""

    def __init__(self, pool: asyncpg.Pool, push: PushSender, *, poll_seconds: float = 30.0) -> None:
        self._pool = pool
        self._push = push
        self._poll_seconds = poll_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            log.info("proactive scheduler started", extra={"poll_seconds": self._poll_seconds})

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                log.exception("scheduler tick failed")
            await asyncio.sleep(self._poll_seconds)

    async def run_once(self, *, now: datetime | None = None) -> int:
        """Deliver all currently-due reminders. Returns how many were delivered."""
        moment = now or datetime.now(UTC)
        delivered = 0
        async with self._pool.acquire() as conn:
            due = await repo.due_reminders(conn, now=moment)
        for reminder in due:
            if await self._deliver(reminder):
                delivered += 1
        return delivered

    async def _deliver(self, reminder: dict) -> bool:
        async with self._pool.acquire() as conn:
            tokens = await repo.get_device_tokens(conn, reminder["user_id"])
        targets = [DeviceTarget(platform=t["platform"], token=t["token"]) for t in tokens]
        note = Notification(
            title="EDITH reminder", body=reminder["text"], data={"kind": "reminder"}
        )
        try:
            await self._push.send(targets, note)
        except Exception:
            log.exception("reminder delivery failed", extra={"reminder_id": reminder["id"]})
            return False
        # Mark delivered even with no devices, so we don't re-notify forever; the
        # reminder is still visible via list_reminders.
        async with self._pool.acquire() as conn:
            await repo.mark_reminder_delivered(conn, reminder["id"])
        return True
