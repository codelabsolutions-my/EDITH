"""EDITH's foundational tools, as a single built-in connector.

Registered into the *existing* connector registry so the agent core has one tool
code path. ``current_time`` and ``web_lookup`` are stateless AUTO tools;
``remember``/``recall`` are AUTO tools wired to a per-user
:class:`~app.agent.memory.Memory` store.

The store is injected per invocation via ``ConnectorContext.extra["memory"]`` (the
session passes the live ``Memory`` there). When absent — e.g. the connector
conformance suite constructs a bare context — the tools fall back to a
module-level default store so they remain callable and valid.

**TODO(M1):** the default store is acceptable for M0 only; M1 swaps the injected
``Memory`` for the Postgres-backed implementation (the interface is unchanged).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...connectors.base import (
    AuthKind,
    Connector,
    ConnectorContext,
    ConnectorManifest,
    Tool,
    ToolClass,
)
from ...connectors.registry import register
from ..memory import Memory

# Fallback store used only when a context carries no injected Memory (M0 / tests).
_DEFAULT_MEMORY = Memory()


@register
class FoundationalConnector(Connector):
    """Built-in tools every EDITH user has: memory, time, lightweight lookup."""

    manifest = ConnectorManifest(
        key="foundational",
        name="Foundational",
        description="EDITH's built-in tools: remember, recall, current time, web lookup.",
        auth=AuthKind.NONE,
        maintainer="edith-core",
        official=True,
        tags=("builtin",),
    )

    def tools(self, ctx: ConnectorContext) -> list[Tool]:
        memory = ctx.extra.get("memory")
        if not isinstance(memory, Memory):
            memory = _DEFAULT_MEMORY
        user_id = ctx.user_id

        async def remember(text: str) -> dict[str, Any]:
            await memory.remember(user_id, text)
            return {"stored": text}

        async def recall(query: str) -> dict[str, Any]:
            facts = await memory.recall(user_id, query)
            return {"memories": facts}

        return [
            Tool(
                name="current_time",
                description="Get the current date and time in ISO-8601 (UTC).",
                parameters={"type": "object", "properties": {}},
                tool_class=ToolClass.AUTO,
                handler=self._current_time,
            ),
            Tool(
                name="web_lookup",
                description="Look up a fact on the web (stub in M0 — returns a canned result).",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "What to look up."}},
                    "required": ["query"],
                },
                tool_class=ToolClass.AUTO,
                handler=self._web_lookup,
            ),
            Tool(
                name="remember",
                description="Remember a durable fact about the user for later.",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The fact to remember."}
                    },
                    "required": ["text"],
                },
                tool_class=ToolClass.AUTO,
                handler=remember,
            ),
            Tool(
                name="recall",
                description="Recall remembered facts relevant to a query.",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "What to recall."}},
                    "required": ["query"],
                },
                tool_class=ToolClass.AUTO,
                handler=recall,
            ),
        ]

    async def _current_time(self) -> dict[str, Any]:
        return {"now": datetime.now(UTC).isoformat()}

    async def _web_lookup(self, query: str) -> dict[str, Any]:
        # M0 makes NO real network calls — return a canned, clearly-stubbed result.
        # TODO(M1+): wire to a real search API behind a connector credential.
        return {
            "query": query,
            "result": "Stubbed web lookup (no network in M0).",
            "stub": True,
        }
