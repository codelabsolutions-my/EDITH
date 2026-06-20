"""Adapter from the connector registry to LLM tool specs + dispatch.

``ToolCatalog`` is the agent core's only view of the available tools. It builds
:class:`~app.agent.llm.ToolSpec` objects from ``registry.all()`` and resolves a
tool name back to its live :class:`~app.connectors.base.Tool` for execution. There
is no second registry — connectors (including the built-in foundational one) are
the single source of truth.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..connectors.base import Connector, ConnectorContext, Tool
from ..connectors.registry import ConnectorRegistry
from .llm import ToolSpec

# Resolves a connector key to its credentials (None in M0 — identity-only).
CredLookup = Callable[[str], dict[str, Any] | None]


class ToolCatalog:
    """Builds tool specs and dispatches tool calls over the connector registry."""

    def __init__(
        self,
        registry: ConnectorRegistry,
        user_id: str,
        cred_lookup: CredLookup,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._registry = registry
        self._user_id = user_id
        self._cred_lookup = cred_lookup
        self._extra = extra or {}

    def _ctx(self, connector: Connector) -> ConnectorContext:
        return ConnectorContext(
            user_id=self._user_id,
            credentials=self._cred_lookup(connector.manifest.key),
            extra=dict(self._extra),
        )

    def _resolve_names(self) -> dict[str, Tool]:
        """Map exposed tool name -> Tool, namespacing only on collision.

        Tool names are kept bare while globally unique (foundational + example_echo
        are). If two connectors expose the same name, the *first* keeps the bare
        name and later ones are exposed as ``"{connector_key}.{tool_name}"``.
        """
        resolved: dict[str, Tool] = {}
        for connector in self._registry.all():
            for tool in connector.tools(self._ctx(connector)):
                name = tool.name
                if name in resolved:
                    name = f"{connector.manifest.key}.{tool.name}"
                resolved[name] = tool
        return resolved

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(name=name, description=tool.description, parameters=tool.parameters)
            for name, tool in self._resolve_names().items()
        ]

    def lookup(self, name: str) -> Tool | None:
        return self._resolve_names().get(name)
