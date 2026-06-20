"""A minimal reference connector.

It needs no auth and exposes two tools — one ``AUTO`` and one ``CONFIRM`` — to
demonstrate the contract and the confirmation gate. Copy this file as the
starting point for a real connector.
"""

from __future__ import annotations

from typing import Any

from ..base import (
    AuthKind,
    Connector,
    ConnectorContext,
    ConnectorManifest,
    Tool,
    ToolClass,
)
from ..registry import register


@register
class EchoConnector(Connector):
    manifest = ConnectorManifest(
        key="example_echo",
        name="Echo (example)",
        description="Reference connector used in docs and tests.",
        auth=AuthKind.NONE,
        maintainer="edith-core",
        official=True,
        tags=("example",),
    )

    def tools(self, ctx: ConnectorContext) -> list[Tool]:
        return [
            Tool(
                name="echo",
                description="Echo the given text back to the user.",
                parameters={
                    "type": "object",
                    "properties": {"text": {"type": "string", "description": "Text to echo."}},
                    "required": ["text"],
                },
                tool_class=ToolClass.AUTO,  # reversible / harmless -> auto
                handler=self._echo,
            ),
            Tool(
                name="self_destruct",
                description="A pretend irreversible action, to show the confirm gate.",
                parameters={
                    "type": "object",
                    "properties": {},
                },
                tool_class=ToolClass.CONFIRM,  # irreversible -> must confirm
                handler=self._self_destruct,
            ),
        ]

    async def _echo(self, text: str) -> dict[str, Any]:
        return {"echo": text}

    async def _self_destruct(self) -> dict[str, Any]:
        return {"status": "would have self-destructed (this is only an example)"}
