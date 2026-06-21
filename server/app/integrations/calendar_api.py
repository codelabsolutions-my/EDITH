"""Google Calendar REST API client (read-only).

The OAuth backend for the calendar connector. Lists upcoming events from the user's
primary calendar with a bearer access token (minted from their stored grant).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

_BASE = "https://www.googleapis.com/calendar/v3"
_REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class CalendarApiError(Exception):
    """Raised on a non-2xx Calendar API response."""


class CalendarApi:
    """Minimal read-only Google Calendar client."""

    def __init__(
        self, access_token: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._token = access_token
        self._transport = transport

    async def list_upcoming(
        self, *, max_results: int = 10, time_min: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Return upcoming events from the primary calendar, soonest first."""
        start = (time_min or datetime.now(UTC)).isoformat()
        params: dict[str, Any] = {
            "timeMin": start,
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client:
            resp = await client.get(
                f"{_BASE}/calendars/primary/events", params=params, headers=headers
            )
        if resp.status_code != 200:
            raise CalendarApiError(f"Calendar API -> {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        return [_parse_event(item) for item in (body.get("items") or [])]


def _parse_event(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": item.get("summary", "(no title)"),
        "start": _when(item.get("start", {})),
        "end": _when(item.get("end", {})),
        "location": item.get("location", ""),
    }


def _when(slot: dict[str, Any]) -> str:
    # All-day events use "date"; timed events use "dateTime".
    return slot.get("dateTime") or slot.get("date") or ""
