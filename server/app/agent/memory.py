"""In-memory conversational memory for M0.

This is the M0 implementation of EDITH's memory: a per-user store the agent loop
recalls from at turn start (injected into the system prompt) and the foundational
``remember``/``recall`` tools write to and read from.

**TODO(M1):** swap for the Postgres ``memories`` table with tsvector lexical
recall and detached LLM extraction (see ``docs/specs/phase-1-data.md``). The
``Memory`` interface below is the seam that swap targets — the agent loop and the
foundational connector depend on it, not on the dict.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict


class Memory:
    """A per-user durable-fact store. M0: an in-process dict, no persistence."""

    def __init__(self) -> None:
        # TODO(M1): replace with Postgres-backed storage keyed by user_id.
        self._by_user: dict[str, list[str]] = defaultdict(list)

    async def remember(self, user_id: str, text: str) -> None:
        """Store a durable fact for ``user_id``."""
        text = text.strip()
        if text:
            self._by_user[user_id].append(text)

    async def recall(self, user_id: str, query: str, *, limit: int = 6) -> list[str]:
        """Return up to ``limit`` remembered facts relevant to ``query``.

        M0 uses a trivial case-insensitive substring match, falling back to the
        most recent facts when the query matches nothing. **TODO(M1):** tsvector
        ranked recall plus always-on high-importance profile memories.
        """
        facts = self._by_user.get(user_id, [])
        if not facts:
            return []
        q = query.lower().strip()
        if q:
            matched = [f for f in facts if any(tok in f.lower() for tok in q.split())]
            if matched:
                return matched[-limit:]
        return facts[-limit:]

    async def extract_after_turn(self, user_id: str, user_text: str, reply_text: str) -> None:
        """Detached post-turn extraction. M0: a no-op placeholder.

        Runs off the latency path after ``TurnComplete``. **TODO(M1):** a
        lightweight LLM/heuristic pass that extracts durable facts, dedupes, and
        inserts them with type/source/importance.
        """
        await asyncio.sleep(0)  # cooperative yield; nothing extracted in M0
