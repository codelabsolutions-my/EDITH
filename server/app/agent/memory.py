"""EDITH's conversational memory: the ``Memory`` seam + two implementations.

The agent loop recalls from a ``Memory`` at turn start (injected into the system
prompt) and the foundational ``remember``/``recall`` tools read/write it. Two
implementations share the seam:

- :class:`InMemoryMemory` — a per-process dict. Zero setup; used in unit tests and
  whenever no database is wired (the connector conformance suite, the text demo
  without a DB).
- :class:`PgMemory` — the durable M1 store backed by the Postgres ``memories``
  table with ``tsvector`` lexical recall.

``Memory`` is an ABC so both implementations type-check identically and the
foundational connector's ``isinstance(memory, Memory)`` guard accepts either.
"""

from __future__ import annotations

import abc
import asyncio
from collections import defaultdict

import asyncpg


class Memory(abc.ABC):
    """A per-user durable-fact store — the seam the agent loop depends on."""

    @abc.abstractmethod
    async def remember(self, user_id: str, text: str) -> None:
        """Store a durable fact for ``user_id``."""

    @abc.abstractmethod
    async def recall(self, user_id: str, query: str, *, limit: int = 6) -> list[str]:
        """Return up to ``limit`` remembered facts relevant to ``query``."""

    async def extract_after_turn(self, user_id: str, user_text: str, reply_text: str) -> None:
        """Detached post-turn fact extraction. Default: a no-op placeholder.

        Runs off the latency path after ``TurnComplete``. **TODO:** a lightweight
        LLM/heuristic pass that extracts durable facts, dedupes, and inserts them
        with type/source/importance. Until then explicit ``remember`` is the path.
        """
        await asyncio.sleep(0)  # cooperative yield; nothing extracted yet


class InMemoryMemory(Memory):
    """A per-process dict store. No persistence — tests and DB-less runs."""

    def __init__(self) -> None:
        self._by_user: dict[str, list[str]] = defaultdict(list)

    async def remember(self, user_id: str, text: str) -> None:
        text = text.strip()
        if text:
            self._by_user[user_id].append(text)

    async def recall(self, user_id: str, query: str, *, limit: int = 6) -> list[str]:
        """Case-insensitive substring match, falling back to the most recent facts."""
        facts = self._by_user.get(user_id, [])
        if not facts:
            return []
        q = query.lower().strip()
        if q:
            matched = [f for f in facts if any(tok in f.lower() for tok in q.split())]
            if matched:
                return matched[-limit:]
        return facts[-limit:]


class PgMemory(Memory):
    """Durable per-user memory backed by the Postgres ``memories`` table.

    Recall ranks by ``ts_rank`` over the ``search_vector`` (a ``websearch``-style
    query), falling back to the most recent facts when the query matches nothing —
    so EDITH still has context for an out-of-vocabulary ask.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def remember(self, user_id: str, text: str, *, source: str = "tool") -> None:
        text = text.strip()
        if not text:
            return
        await self._pool.execute(
            """
            INSERT INTO memories (user_id, type, content, source, importance)
            VALUES ($1, 'fact', $2, $3, 1)
            """,
            user_id,
            text,
            source,
        )

    async def recall(self, user_id: str, query: str, *, limit: int = 6) -> list[str]:
        query = query.strip()
        if query:
            rows = await self._pool.fetch(
                """
                SELECT content
                FROM memories
                WHERE user_id = $1
                  AND search_vector @@ websearch_to_tsquery('english', $2)
                ORDER BY ts_rank(search_vector, websearch_to_tsquery('english', $2)) DESC,
                         created_at DESC
                LIMIT $3
                """,
                user_id,
                query,
                limit,
            )
            if rows:
                return [r["content"] for r in rows]
        # Fallback: most-recent facts so EDITH still has some context.
        rows = await self._pool.fetch(
            "SELECT content FROM memories WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
            user_id,
            limit,
        )
        return list(reversed([r["content"] for r in rows]))
