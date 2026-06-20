"""Connector registry, discovery, and validation.

Connectors register themselves with the default :class:`ConnectorRegistry`
(usually via the :func:`register` decorator). The agent core looks them up by
key. :func:`validate_connector` enforces the contract and is also run by the
conformance test suite (``tests/test_connectors.py``).
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from types import ModuleType

from .base import (
    AuthKind,
    Connector,
    ConnectorContext,
    ConnectorManifest,
    Tool,
    ToolClass,
)

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ConnectorError(ValueError):
    """Raised when a connector violates the contract."""


def validate_connector(connector: Connector) -> None:
    """Validate a connector instance against the contract.

    Raises :class:`ConnectorError` on the first problem found.
    """
    manifest = getattr(connector, "manifest", None)
    if not isinstance(manifest, ConnectorManifest):
        raise ConnectorError(
            f"{type(connector).__name__} must set `manifest` to a ConnectorManifest"
        )

    if not _KEY_RE.match(manifest.key):
        raise ConnectorError(
            f"connector key {manifest.key!r} must be snake_case (^[a-z][a-z0-9_]*$)"
        )

    if manifest.auth is AuthKind.OAUTH2 and manifest.oauth is None:
        raise ConnectorError(f"{manifest.key}: auth=oauth2 requires an `oauth` config")

    # Tools must be well-formed.
    ctx = ConnectorContext(user_id="conformance-check")
    tools = connector.tools(ctx)
    if not isinstance(tools, list):
        raise ConnectorError(f"{manifest.key}: tools() must return a list[Tool]")

    seen: set[str] = set()
    for tool in tools:
        _validate_tool(manifest.key, tool, seen)


def _validate_tool(key: str, tool: Tool, seen: set[str]) -> None:
    if not isinstance(tool, Tool):
        raise ConnectorError(f"{key}: tools() must contain Tool instances")
    if not tool.name:
        raise ConnectorError(f"{key}: a tool has an empty name")
    if tool.name in seen:
        raise ConnectorError(f"{key}: duplicate tool name {tool.name!r}")
    seen.add(tool.name)
    if not isinstance(tool.tool_class, ToolClass):
        raise ConnectorError(f"{key}.{tool.name}: tool_class must be a ToolClass")
    if not isinstance(tool.parameters, dict) or tool.parameters.get("type") != "object":
        raise ConnectorError(
            f"{key}.{tool.name}: parameters must be a JSON-Schema object "
            '(a dict with "type": "object")'
        )
    if not inspect.iscoroutinefunction(tool.handler):
        raise ConnectorError(f"{key}.{tool.name}: handler must be an async function")


class ConnectorRegistry:
    """Holds the set of available connectors, keyed by manifest key."""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector | type[Connector]) -> Connector:
        """Register a connector instance or class. Returns the instance.

        Usable as a decorator on a :class:`Connector` subclass.
        """
        instance = connector() if isinstance(connector, type) else connector
        validate_connector(instance)
        key = instance.manifest.key
        if key in self._connectors:
            raise ConnectorError(f"duplicate connector key: {key!r}")
        self._connectors[key] = instance
        return instance

    def get(self, key: str) -> Connector | None:
        return self._connectors.get(key)

    def all(self) -> list[Connector]:
        return list(self._connectors.values())

    def keys(self) -> list[str]:
        return list(self._connectors)

    def discover(self, package: ModuleType) -> None:
        """Import every submodule of ``package`` so connectors self-register."""
        if not hasattr(package, "__path__"):
            return
        for info in pkgutil.iter_modules(package.__path__):
            importlib.import_module(f"{package.__name__}.{info.name}")


#: The default, process-wide registry.
registry = ConnectorRegistry()


def register(connector: type[Connector]) -> type[Connector]:
    """Class decorator that registers a connector with the default registry."""
    registry.register(connector)
    return connector
