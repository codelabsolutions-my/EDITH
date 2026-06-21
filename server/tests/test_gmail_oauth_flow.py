"""End-to-end Gmail OAuth flow with Google mocked.

connect → (Google) → callback stores an encrypted grant in provider_accounts →
credentials.gmail_access_token decrypts it back. Proves the whole wiring without a
real Google client. Skips if Postgres is unreachable.
"""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

import asyncpg
import pytest
from app.config import get_settings, reset_settings_cache
from app.integrations.google_oauth import GMAIL_READONLY_SCOPE, TokenResponse
from app.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import TEST_DATABASE_URL, reset_db


class FakeGoogleOAuth:
    """Stand-in for GoogleOAuth — no network."""

    def __init__(self, client_id: str, client_secret: str, *, transport=None) -> None:
        pass

    def build_auth_url(self, *, redirect_uri: str, scopes: list[str], state: str) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"

    async def exchange_code(self, code: str, redirect_uri: str) -> TokenResponse:
        return TokenResponse(
            access_token="access-AAA",
            refresh_token="refresh-BBB",
            expires_in=3600,
            scope=GMAIL_READONLY_SCOPE,
        )

    async def fetch_userinfo(self, access_token: str) -> dict:
        return {"sub": "google-sub-1", "email": "ian@gmail.com"}


@pytest.fixture
def google_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr("app.integrations.router.GoogleOAuth", FakeGoogleOAuth)
    reset_settings_cache()
    yield
    reset_settings_cache()


def _login(client: TestClient, email: str) -> tuple[str, str]:
    body = client.post("/auth/dev-login", json={"email": email, "display_name": "Ian"}).json()
    return body["access_token"], body["user"]["id"]


def test_connect_redirects_then_callback_stores_grant(pg_dsn: str, google_env) -> None:
    async def _reset() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=2)
        assert pool is not None
        await reset_db(pool)
        await pool.close()

    asyncio.run(_reset())

    app = create_app()
    with TestClient(app) as client:
        access, user_id = _login(client, "ian@gmail.com")

        # 1) connect → redirect to Google with a signed state.
        r = client.get(
            "/integrations/google/gmail/connect", params={"token": access}, follow_redirects=False
        )
        assert r.status_code in (302, 307), r.text
        state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]

        # 2) Google redirects back with a code; we store the grant.
        cb = client.get(
            "/integrations/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        assert cb.status_code == 200
        assert "connected" in cb.text.lower()

    # The grant is stored encrypted, and credentials resolves a usable token.
    async def _check() -> str | None:
        pool = await asyncpg.create_pool(TEST_DATABASE_URL, min_size=1, max_size=2)
        assert pool is not None
        try:
            row = await pool.fetchrow(
                "SELECT scopes, access_token_enc FROM provider_accounts "
                "WHERE user_id = $1 AND provider = 'google'",
                __import__("uuid").UUID(user_id),
            )
            assert row is not None
            assert GMAIL_READONLY_SCOPE in row["scopes"]
            assert row["access_token_enc"] is not None  # stored as ciphertext bytes
            from app.integrations.credentials import google_access_token

            grant = await google_access_token(pool, get_settings(), user_id)
            return grant[0] if grant else None
        finally:
            await pool.close()

    token = asyncio.run(_check())
    assert token == "access-AAA"  # decrypted back out


def test_connect_requires_valid_jwt(google_env) -> None:
    app = create_app()
    client = TestClient(app)
    r = client.get(
        "/integrations/google/gmail/connect", params={"token": "not-a-jwt"}, follow_redirects=False
    )
    assert r.status_code == 401
