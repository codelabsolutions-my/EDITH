"""Gmail connector — read the user's inbox. OAuth (preferred) or IMAP (fallback).

Two backends behind one set of tools:

- **OAuth / Gmail API** (preferred): the session injects a fresh access token
  (minted from the user's encrypted OAuth grant — see ``integrations``) as
  ``ctx.credentials["gmail_access_token"]``; reads go through the official Gmail
  REST API. This is the proper, revocable, least-privilege path (``gmail.readonly``).
- **IMAP / App Password** (dev fallback): if no OAuth grant is present but
  ``GMAIL_ADDRESS`` + ``GMAIL_APP_PASSWORD`` are set, read over IMAP SSL.

Reading is non-destructive, so both tools are ``AUTO``. With neither backend
configured the tools stay inert and tell the user how to connect.
"""

from __future__ import annotations

import asyncio
import contextlib
import email
import imaplib
from email.header import decode_header, make_header
from email.message import Message
from typing import Any, Protocol

from ..config import get_settings
from ..integrations.gmail_api import GmailApi
from ..integrations.google_oauth import AUTHORIZE_URL, GMAIL_READONLY_SCOPE, TOKEN_URL
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

_SNIPPET_CHARS = 600
_IMAP_TIMEOUT = 20


class _Backend(Protocol):
    async def recent(self, limit: int, unread_only: bool) -> list[dict[str, Any]]: ...
    async def search(self, query: str, limit: int) -> list[dict[str, Any]]: ...


@register
class GmailConnector(Connector):
    """Reads recent / matching emails via the Gmail API (OAuth) or IMAP."""

    manifest = ConnectorManifest(
        key="gmail",
        name="Gmail",
        description="Read your Gmail inbox (recent messages and searches).",
        auth=AuthKind.OAUTH2,
        oauth=OAuthConfig(
            authorize_url=AUTHORIZE_URL,
            token_url=TOKEN_URL,
            scopes=(GMAIL_READONLY_SCOPE,),
        ),
        maintainer="edith-core",
        official=True,
        tags=("email", "google"),
    )

    def tools(self, ctx: ConnectorContext) -> list[Tool]:
        backend = self._resolve_backend(ctx)

        async def read_recent_emails(limit: int = 5, unread_only: bool = False) -> dict[str, Any]:
            """Return the most recent emails (optionally only unread)."""
            if backend is None:
                return _not_connected()
            emails = await backend.recent(_clamp(limit), unread_only)
            return {"connected": True, "count": len(emails), "emails": emails}

        async def search_emails(query: str, limit: int = 5) -> dict[str, Any]:
            """Search the inbox for ``query``."""
            if backend is None:
                return _not_connected()
            emails = await backend.search(query, _clamp(limit))
            return {"connected": True, "query": query, "count": len(emails), "emails": emails}

        return [
            Tool(
                name="read_recent_emails",
                description="Read the user's most recent emails. Use for 'read my emails', "
                "'any new mail', 'what's in my inbox'. Set unread_only for unread mail.",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "How many to return (1-20)."},
                        "unread_only": {"type": "boolean", "description": "Only unread emails."},
                    },
                },
                tool_class=ToolClass.AUTO,
                handler=read_recent_emails,
            ),
            Tool(
                name="search_emails",
                description="Search the user's inbox for emails matching a query "
                "(sender, subject, or body text).",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "What to search for."},
                        "limit": {"type": "integer", "description": "How many to return (1-20)."},
                    },
                    "required": ["query"],
                },
                tool_class=ToolClass.AUTO,
                handler=search_emails,
            ),
        ]

    @staticmethod
    def _resolve_backend(ctx: ConnectorContext) -> _Backend | None:
        creds = ctx.credentials or {}
        token = creds.get("gmail_access_token")
        if token:
            return _GmailApiBackend(str(token))
        if creds.get("address") and creds.get("password"):
            return _ImapBackend(
                {
                    "host": creds.get("host", "imap.gmail.com"),
                    "address": creds["address"],
                    "password": creds["password"],
                }
            )
        s = get_settings()
        if s.GMAIL_ADDRESS and s.GMAIL_APP_PASSWORD:
            return _ImapBackend(
                {
                    "host": s.GMAIL_IMAP_HOST,
                    "address": s.GMAIL_ADDRESS,
                    "password": s.GMAIL_APP_PASSWORD,
                }
            )
        return None


# ─── backends ────────────────────────────────────────────────────────────────


class _GmailApiBackend:
    """OAuth backend over the Gmail REST API."""

    def __init__(self, access_token: str) -> None:
        self._api = GmailApi(access_token)

    async def recent(self, limit: int, unread_only: bool) -> list[dict[str, Any]]:
        return await self._api.list_messages(max_results=limit, unread_only=unread_only)

    async def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        return await self._api.list_messages(max_results=limit, query=query)


class _ImapBackend:
    """App-password backend over IMAP SSL (runs blocking IMAP off the event loop)."""

    def __init__(self, creds: dict[str, str]) -> None:
        self._creds = creds

    async def recent(self, limit: int, unread_only: bool) -> list[dict[str, Any]]:
        criteria = "UNSEEN" if unread_only else "ALL"
        return await asyncio.to_thread(_fetch_emails, self._creds, criteria, None, limit)

    async def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        return await asyncio.to_thread(_fetch_emails, self._creds, "ALL", query, limit)


def _not_connected() -> dict[str, Any]:
    return {
        "connected": False,
        "message": (
            "Gmail is not connected. Connect it with Google sign-in "
            "(GET /integrations/google/gmail/connect), or set GMAIL_ADDRESS + "
            "GMAIL_APP_PASSWORD in server/.env for the IMAP fallback."
        ),
    }


def _clamp(limit: int) -> int:
    try:
        return max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        return 5


# ─── IMAP helpers ─────────────────────────────────────────────────────────────


def _fetch_emails(
    creds: dict[str, str], criteria: str, query: str | None, limit: int
) -> list[dict[str, Any]]:
    """Blocking IMAP fetch. Run via ``asyncio.to_thread`` — never on the event loop."""
    imap = imaplib.IMAP4_SSL(creds["host"], timeout=_IMAP_TIMEOUT)
    try:
        imap.login(creds["address"], creds["password"])
        imap.select("INBOX", readonly=True)
        if query:
            typ, data = imap.search(None, criteria, "TEXT", f'"{query}"')
        else:
            typ, data = imap.search(None, criteria)
        if typ != "OK" or not data or not data[0]:
            return []
        ids = data[0].split()[-limit:]
        out: list[dict[str, Any]] = []
        for msg_id in reversed(ids):  # newest first
            typ, raw = imap.fetch(msg_id, "(RFC822)")
            if typ != "OK" or not raw or not isinstance(raw[0], tuple):
                continue
            out.append(_parse_message(email.message_from_bytes(raw[0][1])))
        return out
    finally:
        with contextlib.suppress(Exception):
            imap.logout()


def _parse_message(msg: Message) -> dict[str, Any]:
    """Extract a content-light summary of a message. Pure — unit-testable."""
    return {
        "from": _decode(msg.get("From", "")),
        "subject": _decode(msg.get("Subject", "")),
        "date": _decode(msg.get("Date", "")),
        "snippet": _body_snippet(msg),
    }


def _decode(value: str) -> str:
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return value.strip()


def _body_snippet(msg: Message) -> str:
    text = " ".join(_extract_plain_text(msg).split())  # collapse whitespace
    return text[:_SNIPPET_CHARS]


def _extract_plain_text(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(
                part.get("Content-Disposition", "")
            ):
                return _payload_text(part)
        return ""
    return _payload_text(msg)


def _payload_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return payload.decode("utf-8", errors="replace")
