"""WhatsApp connector — send via EDITH's own number (Business Cloud API).

Sending a message is external + irreversible → ``CONFIRM`` (the user must approve
before it goes). Credentials are app-level (one business number) for now; per-user
sender identity comes later. Inert with a setup hint when unconfigured.

NOTE: this is the outbound Cloud-API channel only. Reading/replying to the user's
*personal* WhatsApp is Android on-device (NotificationListenerService) — a different
track, never done server-side.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..integrations.whatsapp_api import WhatsAppClient
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
class WhatsAppConnector(Connector):
    """Send WhatsApp messages from EDITH's business number."""

    manifest = ConnectorManifest(
        key="whatsapp",
        name="WhatsApp",
        description="Send a WhatsApp message from EDITH's number (Business Cloud API).",
        auth=AuthKind.API_KEY,
        maintainer="edith-core",
        official=True,
        tags=("messaging", "whatsapp"),
    )

    def tools(self, ctx: ConnectorContext) -> list[Tool]:
        async def send_whatsapp_message(to: str, text: str) -> dict[str, Any]:
            """Send a WhatsApp text message to an E.164 phone number."""
            s = get_settings()
            if not s.WHATSAPP_PHONE_NUMBER_ID or not s.WHATSAPP_ACCESS_TOKEN:
                return {
                    "sent": False,
                    "message": (
                        "WhatsApp is not configured. Set WHATSAPP_PHONE_NUMBER_ID and "
                        "WHATSAPP_ACCESS_TOKEN (Business Cloud API) in server/.env."
                    ),
                }
            client = WhatsAppClient(
                phone_number_id=s.WHATSAPP_PHONE_NUMBER_ID,
                access_token=s.WHATSAPP_ACCESS_TOKEN,
                api_version=s.WHATSAPP_API_VERSION,
            )
            result = await client.send_text(to, text)
            message_id = ""
            messages = result.get("messages") or []
            if messages:
                message_id = messages[0].get("id", "")
            return {"sent": True, "to": to, "message_id": message_id}

        return [
            Tool(
                name="send_whatsapp_message",
                description="Send a WhatsApp message from EDITH's number to a phone number "
                "(E.164, e.g. +60123456789). External send — always confirmed first.",
                parameters={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient phone number (E.164)."},
                        "text": {"type": "string", "description": "The message to send."},
                    },
                    "required": ["to", "text"],
                },
                tool_class=ToolClass.CONFIRM,  # external/irreversible → confirm gate
                handler=send_whatsapp_message,
            ),
        ]
