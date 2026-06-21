"""Gmail connector: parsing, not-connected behaviour, and IMAP fetch (mocked)."""

from __future__ import annotations

import asyncio
from email.message import EmailMessage

from app.connectors.base import ConnectorContext
from app.connectors.gmail import (
    GmailConnector,
    _clamp,
    _GmailApiBackend,
    _ImapBackend,
    _parse_message,
)


def _sample_email(
    subject: str = "Lunch?", body: str = "Are you free   for lunch today?"
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "Aisyah <aisyah@example.com>"
    msg["Subject"] = subject
    msg["Date"] = "Mon, 21 Jun 2026 09:00:00 +0800"
    msg.set_content(body)
    return msg


def test_parse_message_extracts_fields_and_collapses_whitespace() -> None:
    parsed = _parse_message(_sample_email())
    assert parsed["from"] == "Aisyah <aisyah@example.com>"
    assert parsed["subject"] == "Lunch?"
    assert "2026" in parsed["date"]
    # Whitespace in the body is collapsed for a clean snippet.
    assert parsed["snippet"] == "Are you free for lunch today?"


def test_clamp_bounds_limit() -> None:
    assert _clamp(0) == 1
    assert _clamp(100) == 20
    assert _clamp(5) == 5
    assert _clamp("bad") == 5  # type: ignore[arg-type]


def test_oauth_token_selects_the_gmail_api_backend() -> None:
    ctx = ConnectorContext(user_id="u", credentials={"gmail_access_token": "ya29.token"})
    backend = GmailConnector._resolve_backend(ctx)
    assert isinstance(backend, _GmailApiBackend)


def test_app_password_creds_select_the_imap_backend() -> None:
    ctx = ConnectorContext(
        user_id="u", credentials={"address": "x@gmail.com", "password": "app-pw"}
    )
    assert isinstance(GmailConnector._resolve_backend(ctx), _ImapBackend)


def test_tools_report_not_connected_without_credentials() -> None:
    # No ctx credentials and (in the test env) no GMAIL_* settings -> inert.
    tools = {t.name: t for t in GmailConnector().tools(ConnectorContext(user_id="u"))}
    result = asyncio.run(tools["read_recent_emails"].handler())
    assert result["connected"] is False
    assert "not connected" in result["message"].lower()


def test_read_recent_emails_via_mocked_imap(monkeypatch) -> None:
    raw = _sample_email(subject="Invoice", body="Your invoice is attached.").as_bytes()

    class FakeIMAP:
        def __init__(self, host: str, timeout: int | None = None) -> None:
            self.host = host

        def login(self, address: str, password: str) -> tuple:
            assert address == "ian@example.com"
            return ("OK", [b""])

        def select(self, mailbox: str, readonly: bool = False) -> tuple:
            assert readonly is True
            return ("OK", [b"2"])

        def search(self, charset, *criteria) -> tuple:
            return ("OK", [b"1 2"])

        def fetch(self, msg_id, spec) -> tuple:
            return ("OK", [(b"1 (RFC822 {123}", raw)])

        def logout(self) -> tuple:
            return ("OK", [b""])

    monkeypatch.setattr("app.connectors.gmail.imaplib.IMAP4_SSL", FakeIMAP)

    ctx = ConnectorContext(
        user_id="u",
        credentials={"address": "ian@example.com", "password": "app-pw", "host": "imap.test"},
    )
    tools = {t.name: t for t in GmailConnector().tools(ctx)}
    result = asyncio.run(tools["read_recent_emails"].handler(limit=2))

    assert result["connected"] is True
    assert result["count"] == 2
    assert result["emails"][0]["subject"] == "Invoice"
    assert "invoice" in result["emails"][0]["snippet"].lower()
