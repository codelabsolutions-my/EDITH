"""WhatsApp Business Cloud API client (send) — the compliant server channel.

This is EDITH's *own number* via the official Meta Cloud API — a separate, optional
reach/SMB channel. It is **not** the personal-assist path (reading the user's own
WhatsApp), which is Android on-device only. Server-side WhatsApp Web scraping is
explicitly rejected (ban/ToS/security); this uses the documented Graph API.
"""

from __future__ import annotations

from typing import Any

import httpx

_REQUEST_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class WhatsAppApiError(Exception):
    """Raised on a non-2xx Cloud API response."""


class WhatsAppClient:
    """Minimal WhatsApp Cloud API send client."""

    def __init__(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        api_version: str = "v21.0",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        self._token = access_token
        self._transport = transport

    async def send_text(self, to: str, body: str) -> dict[str, Any]:
        """Send a plain-text WhatsApp message to an E.164 number."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client:
            resp = await client.post(self._url, json=payload, headers=headers)
        if resp.status_code not in (200, 201):
            raise WhatsAppApiError(f"WhatsApp send -> {resp.status_code}: {resp.text[:200]}")
        body_json: dict[str, Any] = resp.json()
        return body_json
