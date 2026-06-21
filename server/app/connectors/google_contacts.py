"""Google Contacts connector — read/search contacts (OAuth, read-only).

Uses the People API with an access token the session injects as
``ctx.credentials["contacts_access_token"]``. Reads are non-destructive → ``AUTO``.
Connect with ``GET /integrations/google/contacts/connect`` (incremental scope).
"""

from __future__ import annotations

from typing import Any

from ..integrations.contacts_api import ContactsApi
from ..integrations.google_oauth import AUTHORIZE_URL, CONTACTS_READONLY_SCOPE, TOKEN_URL
from .base import (
    AuthKind,
    Connector,
    ConnectorContext,
    ConnectorManifest,
    OAuthConfig,
    Tool,
    ToolClass,
)
from .registry import register


@register
class GoogleContactsConnector(Connector):
    """Reads and searches the user's Google contacts."""

    manifest = ConnectorManifest(
        key="google_contacts",
        name="Google Contacts",
        description="Look up the user's contacts (names, emails, phone numbers).",
        auth=AuthKind.OAUTH2,
        oauth=OAuthConfig(
            authorize_url=AUTHORIZE_URL,
            token_url=TOKEN_URL,
            scopes=(CONTACTS_READONLY_SCOPE,),
        ),
        maintainer="edith-core",
        official=True,
        tags=("contacts", "google"),
    )

    def tools(self, ctx: ConnectorContext) -> list[Tool]:
        token = (ctx.credentials or {}).get("contacts_access_token")

        def _not_connected() -> dict[str, Any]:
            return {
                "connected": False,
                "message": (
                    "Contacts is not connected. Connect it with "
                    "GET /integrations/google/contacts/connect."
                ),
            }

        async def search_contacts(query: str, limit: int = 10) -> dict[str, Any]:
            """Find contacts matching a name/email/phone query."""
            if not token:
                return _not_connected()
            people = await ContactsApi(str(token)).search_contacts(query, max_results=_clamp(limit))
            return {"connected": True, "query": query, "count": len(people), "contacts": people}

        async def list_contacts(limit: int = 25) -> dict[str, Any]:
            """List the user's contacts (most recently modified first)."""
            if not token:
                return _not_connected()
            people = await ContactsApi(str(token)).list_contacts(max_results=_clamp(limit))
            return {"connected": True, "count": len(people), "contacts": people}

        return [
            Tool(
                name="search_contacts",
                description="Find a contact by name, email, or phone. Use for "
                "'what's Ali's number', 'email for my dentist', 'who is Aisyah'.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Name/email/phone to find."},
                        "limit": {"type": "integer", "description": "How many results (1-25)."},
                    },
                    "required": ["query"],
                },
                tool_class=ToolClass.AUTO,
                handler=search_contacts,
            ),
            Tool(
                name="list_contacts",
                description="List the user's contacts.",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "How many to return (1-50)."},
                    },
                },
                tool_class=ToolClass.AUTO,
                handler=list_contacts,
            ),
        ]


def _clamp(limit: int) -> int:
    try:
        return max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return 25
