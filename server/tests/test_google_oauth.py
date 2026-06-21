"""GoogleOAuth client — auth URL, code exchange, refresh, userinfo (mocked)."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from app.integrations.google_oauth import (
    GMAIL_READONLY_SCOPE,
    GoogleOAuth,
    OAuthError,
)


def _oauth(handler) -> GoogleOAuth:
    return GoogleOAuth("client-id", "client-secret", transport=httpx.MockTransport(handler))


def test_build_auth_url_has_offline_consent_and_scope() -> None:
    oauth = _oauth(lambda r: httpx.Response(200))
    url = oauth.build_auth_url(
        redirect_uri="http://localhost:8000/integrations/google/callback",
        scopes=[GMAIL_READONLY_SCOPE],
        state="state-123",
    )
    q = parse_qs(urlparse(url).query)
    assert q["access_type"] == ["offline"]
    assert q["prompt"] == ["consent"]
    assert q["scope"] == [GMAIL_READONLY_SCOPE]
    assert q["state"] == ["state-123"]
    assert q["response_type"] == ["code"]


def test_exchange_code_returns_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/token")
        body = dict(p.split("=") for p in request.content.decode().split("&"))
        assert body["grant_type"] == "authorization_code"
        return httpx.Response(
            200,
            json={
                "access_token": "at-1",
                "refresh_token": "rt-1",
                "expires_in": 3600,
                "scope": GMAIL_READONLY_SCOPE,
            },
        )

    tokens = asyncio.run(_oauth(handler).exchange_code("code-1", "http://cb"))
    assert tokens.access_token == "at-1"
    assert tokens.refresh_token == "rt-1"
    assert tokens.expires_in == 3600


def test_refresh_returns_new_access_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "at-2", "expires_in": 3600})

    tokens = asyncio.run(_oauth(handler).refresh("rt-1"))
    assert tokens.access_token == "at-2"
    assert tokens.refresh_token is None  # refresh responses omit it


def test_token_error_surfaces() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    with pytest.raises(OAuthError):
        asyncio.run(_oauth(handler).exchange_code("bad", "http://cb"))


def test_fetch_userinfo() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer at-1"
        return httpx.Response(200, json={"sub": "google-123", "email": "ian@gmail.com"})

    info = asyncio.run(_oauth(handler).fetch_userinfo("at-1"))
    assert info["sub"] == "google-123"
    assert info["email"] == "ian@gmail.com"


def test_requires_client_credentials() -> None:
    with pytest.raises(OAuthError):
        GoogleOAuth("", "")
