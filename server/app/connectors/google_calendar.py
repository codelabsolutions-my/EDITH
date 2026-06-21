"""Google Calendar connector — read upcoming events (OAuth, read-only).

Uses the Calendar API with an access token the session injects as
``ctx.credentials["calendar_access_token"]`` (minted from the user's encrypted
Google grant). Reading is non-destructive, so the tool is ``AUTO``. With no grant
the tool stays inert and tells the user to connect.

Connect with ``GET /integrations/google/calendar/connect`` (incremental scope —
adds to any existing Google grant, e.g. Gmail).
"""

from __future__ import annotations

from typing import Any

from ..integrations.calendar_api import CalendarApi
from ..integrations.google_oauth import AUTHORIZE_URL, CALENDAR_READONLY_SCOPE, TOKEN_URL
from .base import (
    AuthKind,
    Connector,
    ConnectorContext,
    ConnectorManifest,
    OAuthConfig,
    Tool,
    ToolClass,
)
from .registry import register


@register
class GoogleCalendarConnector(Connector):
    """Reads upcoming events from the user's primary Google Calendar."""

    manifest = ConnectorManifest(
        key="google_calendar",
        name="Google Calendar",
        description="Read your upcoming Google Calendar events.",
        auth=AuthKind.OAUTH2,
        oauth=OAuthConfig(
            authorize_url=AUTHORIZE_URL,
            token_url=TOKEN_URL,
            scopes=(CALENDAR_READONLY_SCOPE,),
        ),
        maintainer="edith-core",
        official=True,
        tags=("calendar", "google"),
    )

    def tools(self, ctx: ConnectorContext) -> list[Tool]:
        token = (ctx.credentials or {}).get("calendar_access_token")

        async def list_upcoming_events(limit: int = 10) -> dict[str, Any]:
            """List the user's upcoming calendar events, soonest first."""
            if not token:
                return {
                    "connected": False,
                    "message": (
                        "Calendar is not connected. Connect it with "
                        "GET /integrations/google/calendar/connect."
                    ),
                }
            events = await CalendarApi(str(token)).list_upcoming(max_results=_clamp(limit))
            return {"connected": True, "count": len(events), "events": events}

        return [
            Tool(
                name="list_upcoming_events",
                description="List the user's upcoming calendar events. Use for "
                "'what's on my calendar', 'my next meeting', 'am I free', 'schedule today'.",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "How many events (1-25)."},
                    },
                },
                tool_class=ToolClass.AUTO,
                handler=list_upcoming_events,
            ),
        ]


def _clamp(limit: int) -> int:
    try:
        return max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        return 10
