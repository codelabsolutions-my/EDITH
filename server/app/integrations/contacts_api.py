"""Google People API client (read-only) — the OAuth backend for the contacts connector.

Lists and searches the user's contacts (names, emails, phone numbers) with a bearer
access token minted from their stored grant.
"""

from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://people.googleapis.com/v1"
_PERSON_FIELDS = "names,emailAddresses,phoneNumbers"
_REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ContactsApiError(Exception):
    """Raised on a non-2xx People API response."""


class ContactsApi:
    """Minimal read-only Google People client."""

    def __init__(
        self, access_token: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._token = access_token
        self._transport = transport

    async def list_contacts(self, *, max_results: int = 25) -> list[dict[str, Any]]:
        params = {
            "personFields": _PERSON_FIELDS,
            "pageSize": max_results,
            "sortOrder": "LAST_MODIFIED_DESCENDING",
        }
        body = await self._get("/people/me/connections", params)
        return [_parse_person(p) for p in (body.get("connections") or [])]

    async def search_contacts(self, query: str, *, max_results: int = 10) -> list[dict[str, Any]]:
        params = {"query": query, "pageSize": max_results, "readMask": _PERSON_FIELDS}
        body = await self._get("/people:searchContacts", params)
        return [_parse_person(r.get("person", {})) for r in (body.get("results") or [])]

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client:
            resp = await client.get(f"{_BASE}{path}", params=params, headers=headers)
        if resp.status_code != 200:
            raise ContactsApiError(f"People API {path} -> {resp.status_code}: {resp.text[:200]}")
        out: dict[str, Any] = resp.json()
        return out


def _parse_person(person: dict[str, Any]) -> dict[str, Any]:
    names = person.get("names") or []
    emails = person.get("emailAddresses") or []
    phones = person.get("phoneNumbers") or []
    return {
        "name": names[0].get("displayName", "") if names else "",
        "emails": [e.get("value", "") for e in emails if e.get("value")],
        "phones": [p.get("value", "") for p in phones if p.get("value")],
    }
