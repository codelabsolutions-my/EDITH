"""Home Assistant connector — read smart-home state (AUTO) and control it (CONFIRM).

Reading device state is non-destructive → ``AUTO``. Actuating a device touches the
physical world → ``CONFIRM`` (the agent confirms before switching anything). Inert
with a setup hint until HOME_ASSISTANT_URL/TOKEN are configured.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..integrations.home_assistant_api import HomeAssistantClient
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
class HomeAssistantConnector(Connector):
    """Read and control the user's Home Assistant devices."""

    manifest = ConnectorManifest(
        key="home_assistant",
        name="Home Assistant",
        description="See and control your smart-home devices via Home Assistant.",
        auth=AuthKind.API_KEY,
        maintainer="edith-core",
        official=True,
        tags=("smart-home",),
    )

    def tools(self, ctx: ConnectorContext) -> list[Tool]:
        def _client() -> HomeAssistantClient | None:
            s = get_settings()
            if not s.HOME_ASSISTANT_URL or not s.HOME_ASSISTANT_TOKEN:
                return None
            return HomeAssistantClient(s.HOME_ASSISTANT_URL, s.HOME_ASSISTANT_TOKEN)

        async def list_devices(domain: str | None = None) -> dict[str, Any]:
            """List smart-home devices and their state (optionally one domain)."""
            client = _client()
            if client is None:
                return _not_connected()
            states = await client.states()
            if domain:
                states = [s for s in states if s["domain"] == domain]
            return {"connected": True, "count": len(states), "devices": states}

        async def set_device(entity_id: str, on: bool) -> dict[str, Any]:
            """Turn a device on or off (e.g. light.kitchen)."""
            client = _client()
            if client is None:
                return _not_connected()
            service = "turn_on" if on else "turn_off"
            result = await client.call_service("homeassistant", service, entity_id)
            return {"done": True, **result}

        return [
            Tool(
                name="list_devices",
                description="List the user's smart-home devices and their state. Use for "
                "'is the light on', 'what's my thermostat', 'list my devices'.",
                parameters={
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": "Optional filter, e.g. light, switch, climate.",
                        },
                    },
                },
                tool_class=ToolClass.AUTO,
                handler=list_devices,
            ),
            Tool(
                name="set_device",
                description="Turn a smart-home device on or off by entity_id "
                "(e.g. light.kitchen). Physical action — confirmed first.",
                parameters={
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "The HA entity id."},
                        "on": {"type": "boolean", "description": "True to turn on, false off."},
                    },
                    "required": ["entity_id", "on"],
                },
                tool_class=ToolClass.CONFIRM,  # actuates the physical world → confirm
                handler=set_device,
            ),
        ]


def _not_connected() -> dict[str, Any]:
    return {
        "connected": False,
        "message": (
            "Home Assistant is not connected. Set HOME_ASSISTANT_URL and a long-lived "
            "HOME_ASSISTANT_TOKEN in server/.env."
        ),
    }
