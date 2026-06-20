"""EDITH connector framework.

Public API for building and registering connectors. See ``README.md`` for the
contributor cookbook.
"""

from __future__ import annotations

from .base import (
    AuthKind,
    Connector,
    ConnectorContext,
    ConnectorManifest,
    OAuthConfig,
    Tool,
    ToolClass,
    ToolHandler,
)
from .registry import (
    ConnectorError,
    ConnectorRegistry,
    register,
    registry,
    validate_connector,
)

__all__ = [
    "AuthKind",
    "Connector",
    "ConnectorContext",
    "ConnectorError",
    "ConnectorManifest",
    "ConnectorRegistry",
    "OAuthConfig",
    "Tool",
    "ToolClass",
    "ToolHandler",
    "register",
    "registry",
    "validate_connector",
]
