"""Home Assistant REST API client — the smart-home backend (P5).

Reads entity states and calls services (turn devices on/off) against a self-hosted
Home Assistant, authenticated with a long-lived access token. The user owns their HA
instance; EDITH just drives its documented REST API.
"""

from __future__ import annotations

from typing import Any

import httpx

_REQUEST_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class HomeAssistantError(Exception):
    """Raised on a non-2xx Home Assistant response."""


class HomeAssistantClient:
    """Minimal Home Assistant REST client (states + service calls)."""

    def __init__(
        self,
        base_url: str,
        access_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token = access_token
        self._transport = transport

    async def states(self) -> list[dict[str, Any]]:
        """Return all entity states (id, state, friendly name)."""
        data = await self._request("GET", "/api/states")
        return [_parse_state(e) for e in (data if isinstance(data, list) else [])]

    async def call_service(self, domain: str, service: str, entity_id: str) -> dict[str, Any]:
        """Call a service on an entity, e.g. (homeassistant, turn_on, light.kitchen)."""
        await self._request(
            "POST", f"/api/services/{domain}/{service}", json={"entity_id": entity_id}
        )
        return {"entity_id": entity_id, "service": f"{domain}.{service}"}

    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client:
            resp = await client.request(method, f"{self._base}{path}", headers=headers, json=json)
        if resp.status_code not in (200, 201):
            raise HomeAssistantError(f"HA {path} -> {resp.status_code}: {resp.text[:200]}")
        return resp.json()


def _parse_state(entity: dict[str, Any]) -> dict[str, Any]:
    attrs = entity.get("attributes") or {}
    entity_id = entity.get("entity_id", "")
    return {
        "entity_id": entity_id,
        "name": attrs.get("friendly_name", entity_id),
        "state": entity.get("state", ""),
        "domain": entity_id.split(".", 1)[0] if "." in entity_id else "",
    }
