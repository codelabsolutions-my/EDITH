"""Gmail REST client — list + get over a mocked Gmail API."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from app.integrations.gmail_api import GmailApi, GmailApiError


def _api(handler) -> GmailApi:
    return GmailApi("access-token", transport=httpx.MockTransport(handler))


def _message(msg_id: str, subject: str) -> dict:
    return {
        "id": msg_id,
        "snippet": f"  preview of {subject}  ",
        "payload": {
            "headers": [
                {"name": "From", "value": "Aisyah <aisyah@example.com>"},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Sun, 21 Jun 2026 09:00:00 +0800"},
            ]
        },
    }


def test_list_messages_lists_then_fetches_each() -> None:
    seen_query = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer access-token"
        path = request.url.path
        if path.endswith("/messages"):
            seen_query["q"] = request.url.params.get("q")
            seen_query["max"] = request.url.params.get("maxResults")
            return httpx.Response(200, json={"messages": [{"id": "a"}, {"id": "b"}]})
        if path.endswith("/messages/a"):
            return httpx.Response(200, json=_message("a", "Invoice"))
        if path.endswith("/messages/b"):
            return httpx.Response(200, json=_message("b", "Lunch"))
        raise AssertionError(f"unexpected path {path}")

    emails = asyncio.run(_api(handler).list_messages(max_results=2, unread_only=True))
    assert seen_query["max"] == "2"
    assert "is:unread" in seen_query["q"]
    assert [e["subject"] for e in emails] == ["Invoice", "Lunch"]
    assert emails[0]["from"] == "Aisyah <aisyah@example.com>"
    assert emails[0]["snippet"] == "preview of Invoice"  # trimmed


def test_search_combines_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            assert request.url.params.get("q") == "from:boss"
            return httpx.Response(200, json={"messages": []})
        raise AssertionError

    emails = asyncio.run(_api(handler).list_messages(query="from:boss"))
    assert emails == []


def test_api_error_raised_on_non_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    with pytest.raises(GmailApiError):
        asyncio.run(_api(handler).list_messages())
