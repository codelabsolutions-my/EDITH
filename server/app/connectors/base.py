"""The EDITH connector contract.

A **connector** exposes a third-party service to the EDITH agent as a set of
**tools**. The agent (an LLM) decides when to call a tool; the server executes it
and feeds the result back into the conversation.

Contributors implement :class:`Connector`. See ``README.md`` in this package for
the step-by-step cookbook. Keep connectors:

* **least-privilege** — request the minimum OAuth scopes, incrementally;
* **honest about risk** — class every external/irreversible tool as ``CONFIRM``;
* **compliant** — official APIs only (no scraping / unofficial clients).
"""

from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolClass(str, Enum):
    """Trust class for a tool — enforced by the agent core.

    ``AUTO`` runs immediately. ``CONFIRM`` requires explicit user confirmation
    before it executes (e.g. send, delete, post, pay, unlock).
    """

    AUTO = "auto"
    CONFIRM = "confirm"


class AuthKind(str, Enum):
    """How a connector authenticates with its service."""

    NONE = "none"
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    DEVICE = "device"  # on-device capability (e.g. Android WhatsApp assist)


@dataclass(frozen=True)
class OAuthConfig:
    """OAuth 2.0 configuration for a connector.

    ``scopes`` are the *baseline* (identity/connect) scopes. Feature-specific
    scopes should be requested incrementally, just-in-time, not all up front.
    """

    authorize_url: str
    token_url: str
    scopes: tuple[str, ...] = ()


# A tool handler is an async callable invoked with keyword arguments that match
# the tool's JSON-Schema ``parameters``. It returns a JSON-serialisable result.
ToolHandler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class Tool:
    """A single action the agent can invoke on a connector."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema (object)
    tool_class: ToolClass
    handler: ToolHandler


@dataclass(frozen=True)
class ConnectorManifest:
    """Static metadata describing a connector."""

    key: str  # unique, snake_case, e.g. "google_calendar"
    name: str  # human label, e.g. "Google Calendar"
    description: str
    auth: AuthKind
    oauth: OAuthConfig | None = None
    version: str = "0.1.0"
    maintainer: str = ""  # GitHub handle
    official: bool = False  # official (core-maintained) vs community
    homepage: str = ""
    tags: tuple[str, ...] = ()


@dataclass
class ConnectorContext:
    """Per-invocation context passed to :meth:`Connector.tools`.

    Carries the acting user and their (already-refreshed) credentials for this
    connector. The agent core constructs this; connectors must never reach for
    global state.
    """

    user_id: str
    credentials: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Connector(abc.ABC):
    """Base class for all connectors.

    Subclasses set :attr:`manifest` and implement :meth:`tools`.
    """

    #: Static metadata. Subclasses must set this to a :class:`ConnectorManifest`.
    manifest: ConnectorManifest

    @abc.abstractmethod
    def tools(self, ctx: ConnectorContext) -> list[Tool]:
        """Return the tools this connector exposes for ``ctx``'s user."""
        raise NotImplementedError
