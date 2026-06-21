"""WhatsApp Cloud API client + connector (CONFIRM send)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from app.connectors.base import ConnectorContext, ToolClass
from app.connectors.whatsapp import WhatsAppConnector
from app.integrations.whatsapp_api import WhatsAppApiError, WhatsAppClient


def _client(handler) -> WhatsAppClient:
    return WhatsAppClient(
        phone_number_id="pnid",
        access_token="tok",
        transport=httpx.MockTransport(handler),
    )


def test_send_text_posts_cloud_api_shape() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.123"}]})

    result = asyncio.run(_client(handler).send_text("+60123456789", "Hai!"))
    assert result["messages"][0]["id"] == "wamid.123"
    assert seen["path"].endswith("/pnid/messages")
    assert seen["auth"] == "Bearer tok"
    assert seen["body"]["messaging_product"] == "whatsapp"
    assert seen["body"]["to"] == "+60123456789"
    assert seen["body"]["text"] == {"body": "Hai!"}


def test_send_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid token")

    with pytest.raises(WhatsAppApiError):
        asyncio.run(_client(handler).send_text("+60123", "x"))


def test_connector_send_is_confirm_class() -> None:
    tool = WhatsAppConnector().tools(ConnectorContext(user_id="u"))[0]
    assert tool.name == "send_whatsapp_message"
    assert tool.tool_class is ToolClass.CONFIRM  # external send must be gated


def test_connector_inert_without_config() -> None:
    # Test env has no WhatsApp settings → reports not configured (no network).
    tool = WhatsAppConnector().tools(ConnectorContext(user_id="u"))[0]
    result = asyncio.run(tool.handler(to="+60123", text="hi"))
    assert result["sent"] is False
    assert "not configured" in result["message"].lower()
