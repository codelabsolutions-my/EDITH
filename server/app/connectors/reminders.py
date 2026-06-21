"""Reminders connector — let the user ask EDITH to remind them later.

``set_reminder`` persists a one-shot reminder the proactive scheduler later pushes.
The model supplies ``remind_at`` as an ISO-8601 timestamp (it computes relative times
like "in 30 minutes" / "tomorrow 9am" from ``current_time`` — ``nemo-super`` is
validated at relative-date math). Setting a reminder is reversible/local → ``AUTO``.

The store is injected via ``ConnectorContext.extra["reminder_store"]`` (the session
passes a Postgres-backed one). Absent — DB-less runs / the conformance suite — the
tools report reminders aren't available rather than failing.
"""

from __future__ import annotations

from typing import Any

from ..proactivity.reminders import ReminderStore, parse_remind_at
from .base import (
    AuthKind,
    Connector,
    ConnectorContext,
    ConnectorManifest,
    Tool,
    ToolClass,
)
from .registry import register


@register
class RemindersConnector(Connector):
    """Set and list proactive reminders."""

    manifest = ConnectorManifest(
        key="reminders",
        name="Reminders",
        description="Ask EDITH to remind you about something at a specific time.",
        auth=AuthKind.NONE,
        maintainer="edith-core",
        official=True,
        tags=("builtin", "proactivity"),
    )

    def tools(self, ctx: ConnectorContext) -> list[Tool]:
        store = ctx.extra.get("reminder_store")
        store = store if isinstance(store, ReminderStore) else None

        async def set_reminder(text: str, remind_at: str) -> dict[str, Any]:
            """Create a reminder. ``remind_at`` is an ISO-8601 timestamp."""
            if store is None:
                return {"ok": False, "message": "Reminders need a database connection."}
            try:
                when = parse_remind_at(remind_at)
            except ValueError:
                return {"ok": False, "message": "remind_at must be an ISO-8601 timestamp."}
            reminder_id = await store.add(text, when)
            return {"ok": True, "id": reminder_id, "text": text, "remind_at": when.isoformat()}

        async def list_reminders() -> dict[str, Any]:
            """List the user's pending reminders."""
            if store is None:
                return {"ok": False, "message": "Reminders need a database connection."}
            items = await store.list()
            return {
                "ok": True,
                "reminders": [
                    {"text": r["text"], "remind_at": r["remind_at"].isoformat()} for r in items
                ],
            }

        return [
            Tool(
                name="set_reminder",
                description="Remind the user about something at a time. Compute remind_at as an "
                "ISO-8601 timestamp from the current time (e.g. 'in 30 min', 'tomorrow 9am').",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "What to remind about."},
                        "remind_at": {
                            "type": "string",
                            "description": "When, as an ISO-8601 timestamp "
                            "(e.g. 2026-06-22T09:00:00+08:00).",
                        },
                    },
                    "required": ["text", "remind_at"],
                },
                tool_class=ToolClass.AUTO,
                handler=set_reminder,
            ),
            Tool(
                name="list_reminders",
                description="List the user's pending reminders.",
                parameters={"type": "object", "properties": {}},
                tool_class=ToolClass.AUTO,
                handler=list_reminders,
            ),
        ]
