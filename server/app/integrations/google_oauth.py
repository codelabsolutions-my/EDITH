"""Google OAuth 2.0 relying-party flow (authorization code + refresh).

Used for incremental, just-in-time API scopes (Gmail read-only first; Calendar /
Contacts reuse this). We request ``access_type=offline`` + ``prompt=consent`` so
Google returns a refresh token, which we store encrypted and use to mint fresh
access tokens without re-prompting.

The client takes an injectable httpx transport so the token exchange/refresh is
testable without hitting Google.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# Gmail read-only — the only Google scope EDITH needs to read mail.
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

_REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class OAuthError(Exception):
    """Raised when an OAuth token exchange/refresh fails."""


@dataclass(frozen=True)
class TokenResponse:
    """Tokens returned by Google's token endpoint."""

    access_token: str
    expires_in: int
    scope: str
    refresh_token: str | None = None  # absent on refresh responses


class GoogleOAuth:
    """Minimal Google OAuth 2.0 client (auth URL, code exchange, refresh)."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not client_id or not client_secret:
            raise OAuthError("Google OAuth requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport

    def build_auth_url(self, *, redirect_uri: str, scopes: list[str], state: str) -> str:
        """Build the consent URL the user is sent to."""
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",  # ask for a refresh token
            "prompt": "consent",  # ensure a refresh token is returned
            "include_granted_scopes": "true",  # incremental authorization
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> TokenResponse:
        """Exchange an authorization code for tokens."""
        return await self._token_request(
            {
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Mint a fresh access token from a stored refresh token."""
        return await self._token_request(
            {"refresh_token": refresh_token, "grant_type": "refresh_token"}
        )

    async def fetch_userinfo(self, access_token: str) -> dict[str, str]:
        """Fetch the account's OIDC userinfo (``sub``, ``email``) with an access token."""
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client:
            resp = await client.get(USERINFO_URL, headers=headers)
        if resp.status_code != 200:
            raise OAuthError(f"userinfo returned {resp.status_code}: {resp.text[:200]}")
        info: dict[str, str] = resp.json()
        return info

    async def _token_request(self, extra: dict[str, str]) -> TokenResponse:
        data = {"client_id": self._client_id, "client_secret": self._client_secret, **extra}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client:
            resp = await client.post(TOKEN_URL, data=data)
        if resp.status_code != 200:
            raise OAuthError(f"token endpoint returned {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        if "access_token" not in body:
            raise OAuthError(f"token response missing access_token: {body}")
        return TokenResponse(
            access_token=body["access_token"],
            expires_in=int(body.get("expires_in", 3600)),
            scope=body.get("scope", ""),
            refresh_token=body.get("refresh_token"),
        )
