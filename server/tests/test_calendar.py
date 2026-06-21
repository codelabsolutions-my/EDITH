"""Google Calendar API client + connector."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from app.connectors.base import ConnectorContext
from app.connectors.google_calendar import GoogleCalendarConnector
from app.integrations.calendar_api import CalendarApi, CalendarApiError


def _api(handler) -> CalendarApi:
    return CalendarApi("access-token", transport=httpx.MockTransport(handler))


def test_list_upcoming_parses_events() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer access-token"
        assert request.url.params.get("singleEvents") == "true"
        assert request.url.params.get("orderBy") == "startTime"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "summary": "Standup",
                        "start": {"dateTime": "2026-06-22T09:00:00+08:00"},
                        "end": {"dateTime": "2026-06-22T09:15:00+08:00"},
                        "location": "Zoom",
                    },
                    {"start": {"date": "2026-06-23"}, "end": {"date": "2026-06-24"}},
                ]
            },
        )

    events = asyncio.run(_api(handler).list_upcoming(max_results=5))
    assert events[0]["summary"] == "Standup"
    assert events[0]["start"] == "2026-06-22T09:00:00+08:00"
    assert events[0]["location"] == "Zoom"
    # All-day event falls back to "date" and a default title.
    assert events[1]["summary"] == "(no title)"
    assert events[1]["start"] == "2026-06-23"


def test_calendar_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    with pytest.raises(CalendarApiError):
        asyncio.run(_api(handler).list_upcoming())


def test_connector_inert_without_token() -> None:
    tools = {t.name: t for t in GoogleCalendarConnector().tools(ConnectorContext(user_id="u"))}
    result = asyncio.run(tools["list_upcoming_events"].handler())
    assert result["connected"] is False
    assert "not connected" in result["message"].lower()


def test_connector_lists_events_with_token(monkeypatch) -> None:
    class FakeCalendarApi:
        def __init__(self, token: str) -> None:
            assert token == "cal-token"

        async def list_upcoming(self, *, max_results: int = 10) -> list[dict]:
            return [{"summary": "Lunch", "start": "x", "end": "y", "location": ""}]

    monkeypatch.setattr("app.connectors.google_calendar.CalendarApi", FakeCalendarApi)
    ctx = ConnectorContext(user_id="u", credentials={"calendar_access_token": "cal-token"})
    tools = {t.name: t for t in GoogleCalendarConnector().tools(ctx)}
    result = asyncio.run(tools["list_upcoming_events"].handler(limit=3))
    assert result["connected"] is True
    assert result["count"] == 1
    assert result["events"][0]["summary"] == "Lunch"
