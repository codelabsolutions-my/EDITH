"""Gmail REST API client (read-only) — the OAuth backend for the gmail connector.

Uses a bearer access token (minted from the user's stored OAuth grant) to list and
read messages via the official Gmail API. The API returns a ``snippet`` and message
headers directly, so no MIME parsing is needed (unlike the IMAP fallback).
"""

from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
_REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_WANT_HEADERS = ("From", "Subject", "Date")


class GmailApiError(Exception):
    """Raised on a non-2xx Gmail API response."""


class GmailApi:
    """Minimal read-only Gmail API client."""

    def __init__(
        self, access_token: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._token = access_token
        self._transport = transport

    async def list_messages(
        self, *, max_results: int = 5, query: str | None = None, unread_only: bool = False
    ) -> list[dict[str, Any]]:
        """Return parsed summaries of the most recent matching messages."""
        q_parts = []
        if unread_only:
            q_parts.append("is:unread")
        if query:
            q_parts.append(query)
        params: dict[str, Any] = {"maxResults": max_results}
        if q_parts:
            params["q"] = " ".join(q_parts)

        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client:
            listing = await self._get(client, "/messages", params, headers)
            ids = [m["id"] for m in (listing.get("messages") or [])]
            out: list[dict[str, Any]] = []
            for msg_id in ids:
                detail = await self._get(
                    client,
                    f"/messages/{msg_id}",
                    {"format": "metadata", "metadataHeaders": list(_WANT_HEADERS)},
                    headers,
                )
                out.append(_parse_message(detail))
            return out

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        resp = await client.get(f"{_BASE}{path}", params=params, headers=headers)
        if resp.status_code != 200:
            raise GmailApiError(f"Gmail API {path} -> {resp.status_code}: {resp.text[:200]}")
        body: dict[str, Any] = resp.json()
        return body


def _parse_message(detail: dict[str, Any]) -> dict[str, Any]:
    headers = {
        h.get("name", "").lower(): h.get("value", "")
        for h in (detail.get("payload", {}).get("headers") or [])
    }
    return {
        "from": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "snippet": (detail.get("snippet") or "").strip(),
    }
