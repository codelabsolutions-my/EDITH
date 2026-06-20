"""Gmail connector — read the user's inbox over IMAP.

A pragmatic, working email reader for the single-user dev path: it authenticates
with a **Gmail App Password** (not the account password) over IMAP SSL, so EDITH can
read mail without a full OAuth relying-party setup. Reading is a non-destructive
action, so both tools are ``AUTO`` (no confirmation gate).

Credentials come from ``ConnectorContext.credentials`` when present (the future
multi-user path) and otherwise fall back to ``GMAIL_ADDRESS`` / ``GMAIL_APP_PASSWORD``
in settings. With neither configured the tools stay inert and tell the user how to
connect rather than erroring.

**TODO(P2):** replace the app-password path with Gmail OAuth + the incremental-scope
credential store (per docs/specs/product-design.md), keyed per user.
"""

from __future__ import annotations

import asyncio
import contextlib
import email
import imaplib
from email.header import decode_header, make_header
from email.message import Message
from typing import Any

from ..config import get_settings
from .base import (
    AuthKind,
    Connector,
    ConnectorContext,
    ConnectorManifest,
    Tool,
    ToolClass,
)
from .registry import register

# Cap how much body text we surface — enough for EDITH to summarise, not the whole mail.
_SNIPPET_CHARS = 600
_IMAP_TIMEOUT = 20


@register
class GmailConnector(Connector):
    """Reads recent / matching emails from the user's Gmail over IMAP."""

    manifest = ConnectorManifest(
        key="gmail",
        name="Gmail",
        description="Read your Gmail inbox (recent messages and searches).",
        auth=AuthKind.API_KEY,  # app password (dev path; OAuth in P2)
        maintainer="edith-core",
        official=True,
        tags=("email", "google"),
    )

    def tools(self, ctx: ConnectorContext) -> list[Tool]:
        creds = self._resolve_credentials(ctx)

        async def read_recent_emails(limit: int = 5, unread_only: bool = False) -> dict[str, Any]:
            """Return the most recent emails (optionally only unread)."""
            if creds is None:
                return _not_connected()
            criteria = "UNSEEN" if unread_only else "ALL"
            emails = await asyncio.to_thread(_fetch_emails, creds, criteria, None, _clamp(limit))
            return {"connected": True, "count": len(emails), "emails": emails}

        async def search_emails(query: str, limit: int = 5) -> dict[str, Any]:
            """Search the inbox (subject/body/sender) for ``query``."""
            if creds is None:
                return _not_connected()
            emails = await asyncio.to_thread(_fetch_emails, creds, "ALL", query, _clamp(limit))
            return {"connected": True, "query": query, "count": len(emails), "emails": emails}

        return [
            Tool(
                name="read_recent_emails",
                description="Read the user's most recent emails. Use for 'read my emails', "
                "'any new mail', 'what's in my inbox'. Set unread_only for unread mail.",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "How many emails to return (1-20).",
                        },
                        "unread_only": {
                            "type": "boolean",
                            "description": "Only return unread emails.",
                        },
                    },
                },
                tool_class=ToolClass.AUTO,  # reading is non-destructive
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
                        "limit": {
                            "type": "integer",
                            "description": "How many emails to return (1-20).",
                        },
                    },
                    "required": ["query"],
                },
                tool_class=ToolClass.AUTO,
                handler=search_emails,
            ),
        ]

    @staticmethod
    def _resolve_credentials(ctx: ConnectorContext) -> dict[str, str] | None:
        if ctx.credentials and ctx.credentials.get("address") and ctx.credentials.get("password"):
            return {
                "host": ctx.credentials.get("host", "imap.gmail.com"),
                "address": ctx.credentials["address"],
                "password": ctx.credentials["password"],
            }
        s = get_settings()
        if s.GMAIL_ADDRESS and s.GMAIL_APP_PASSWORD:
            return {
                "host": s.GMAIL_IMAP_HOST,
                "address": s.GMAIL_ADDRESS,
                "password": s.GMAIL_APP_PASSWORD,
            }
        return None


def _not_connected() -> dict[str, Any]:
    return {
        "connected": False,
        "message": (
            "Gmail is not connected. Add GMAIL_ADDRESS and a Gmail App Password "
            "(GMAIL_APP_PASSWORD) to server/.env to let EDITH read your inbox."
        ),
    }


def _clamp(limit: int) -> int:
    try:
        return max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        return 5


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
    text = _extract_plain_text(msg)
    text = " ".join(text.split())  # collapse whitespace
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
