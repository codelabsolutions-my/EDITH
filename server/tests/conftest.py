"""Shared test fixtures and the in-memory fake transport.

Tests drive async code with ``asyncio.run(...)`` directly (no pytest-asyncio).
The :class:`RecordingTransport` records every outbound event so tests can assert
on the wire-level behaviour the agent loop produces.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import asyncpg
import pytest
from app.events import ConfirmRequest, OutboundEvent, Status
from app.voice.transport import Transport, UserTurn

# Known test secret so tests can mint tokens the app will verify.
TEST_JWT_SECRET = "test-secret-please-change-0123456789abcdef"
# Local docker-compose Postgres (see docker-compose.yml). Integration tests skip
# gracefully when it is not reachable.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://edith:edith@localhost:5434/edith")

# Tables truncated between DB-backed tests (FK-safe order via CASCADE).
_DB_TABLES = (
    "action_log",
    "messages",
    "conversations",
    "memories",
    "refresh_tokens",
    "provider_accounts",
    "users",
)


@pytest.fixture(autouse=True, scope="session")
def _deterministic_env() -> AsyncIterator[None]:
    """Force offline, deterministic settings regardless of a developer's .env.

    Clearing the ILMU key selects ``StubLLM`` (no network); a fixed JWT secret lets
    tests mint tokens the app verifies; ENV=test keeps dev-login enabled.
    """
    from app.config import reset_settings_cache

    os.environ["ILMU_API_KEY"] = ""
    os.environ["ILMU_API_BASE"] = ""
    os.environ["JWT_SECRET"] = TEST_JWT_SECRET
    os.environ["ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    reset_settings_cache()
    yield
    reset_settings_cache()


async def reset_db(pool: asyncpg.Pool) -> None:
    """Truncate all app tables — call at the start of a DB test (same event loop)."""
    await pool.execute(f"TRUNCATE {', '.join(_DB_TABLES)} RESTART IDENTITY CASCADE")


@pytest.fixture
def pg_dsn() -> str:
    """The test Postgres DSN, with migrations applied. Skips if unreachable.

    Returns a connection string (not a live pool): an asyncpg pool is bound to the
    event loop that created it, so each test must build its own pool inside its own
    ``asyncio.run`` to avoid cross-loop errors.
    """
    from app.db import apply_migrations

    async def _ping() -> None:
        conn = await asyncpg.connect(TEST_DATABASE_URL)
        await conn.close()

    try:
        apply_migrations(TEST_DATABASE_URL)
        asyncio.run(_ping())
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"test Postgres not reachable at {TEST_DATABASE_URL}: {exc}")
    return TEST_DATABASE_URL


class RecordingTransport(Transport):
    """A Transport that yields scripted turns and records emitted events.

    ``confirm_answers`` maps an ``action_id`` to the boolean reply to give when the
    loop requests confirmation; a missing id defaults to ``True``.
    """

    def __init__(
        self,
        turns: list[str],
        *,
        confirm_answers: dict[str, bool] | None = None,
    ) -> None:
        self._turns = list(turns)
        self._confirm_answers = confirm_answers or {}
        self.events: list[OutboundEvent] = []
        self.statuses: list[Status] = []
        self.confirm_requests: list[tuple[str, str]] = []
        self._barge_in = asyncio.Event()

    async def pump(self) -> None:
        # The scripted transport needs no inbound pump; turns are pre-seeded.
        return None

    async def user_turns(self) -> AsyncIterator[UserTurn]:
        for text in self._turns:
            yield UserTurn(text=text, audio_present=False)

    async def emit(self, event: OutboundEvent) -> None:
        self.events.append(event)

    async def set_status(self, status: Status) -> None:
        self.statuses.append(status)

    async def request_confirm(self, action_id: str, summary: str) -> bool:
        self.confirm_requests.append((action_id, summary))
        await self.emit(ConfirmRequest(action_id=action_id, summary=summary))
        return self._confirm_answers.get(action_id, True)

    def barge_in_signal(self) -> asyncio.Event:
        return self._barge_in

    async def flush_output(self) -> None:
        return None

    async def close(self) -> None:
        return None
