"""Home Assistant client + connector (read AUTO, control CONFIRM)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from app.connectors.base import ConnectorContext, ToolClass
from app.connectors.home_assistant import HomeAssistantConnector
from app.integrations.home_assistant_api import HomeAssistantClient, HomeAssistantError


def _client(handler) -> HomeAssistantClient:
    return HomeAssistantClient("http://ha.test:8123", "tok", transport=httpx.MockTransport(handler))


def test_states_are_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/states"
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(
            200,
            json=[
                {
                    "entity_id": "light.kitchen",
                    "state": "on",
                    "attributes": {"friendly_name": "Kitchen"},
                },
                {"entity_id": "switch.fan", "state": "off", "attributes": {}},
            ],
        )

    states = asyncio.run(_client(handler).states())
    assert states[0] == {
        "entity_id": "light.kitchen",
        "name": "Kitchen",
        "state": "on",
        "domain": "light",
    }
    assert states[1]["name"] == "switch.fan"  # falls back to entity_id


def test_call_service_posts_entity() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=[])

    result = asyncio.run(_client(handler).call_service("homeassistant", "turn_on", "light.kitchen"))
    assert seen["path"] == "/api/services/homeassistant/turn_on"
    assert seen["body"] == {"entity_id": "light.kitchen"}
    assert result["service"] == "homeassistant.turn_on"


def test_error_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad token")

    with pytest.raises(HomeAssistantError):
        asyncio.run(_client(handler).states())


def test_connector_classes_and_inert() -> None:
    tools = {t.name: t for t in HomeAssistantConnector().tools(ConnectorContext(user_id="u"))}
    # Read is AUTO, actuation is CONFIRM.
    assert tools["list_devices"].tool_class is ToolClass.AUTO
    assert tools["set_device"].tool_class is ToolClass.CONFIRM
    # No HA config in the test env → inert (no network).
    assert asyncio.run(tools["list_devices"].handler())["connected"] is False
    assert (
        asyncio.run(tools["set_device"].handler(entity_id="light.x", on=True))["connected"] is False
    )
