"""OAuth connect + callback routes for Google API integrations (Gmail first).

Flow (just-in-time, incremental scope):
1. ``GET /integrations/google/gmail/connect?token=<our access JWT>`` — authenticate
   the user with our JWT, then redirect them to Google's consent screen. A signed,
   short-lived ``state`` JWT binds the callback to this user (CSRF defence).
2. ``GET /integrations/google/callback?code&state`` — Google redirects here; we
   verify state, exchange the code, fetch userinfo, and store the encrypted grant in
   ``provider_accounts``. From then on the gmail connector reads via the API.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import repositories as repo
from ..auth.crypto import encrypt, load_key
from ..auth.tokens import AuthError, verify_access_token
from ..config import Settings, get_settings
from .google_oauth import (
    CALENDAR_READONLY_SCOPE,
    GMAIL_READONLY_SCOPE,
    GoogleOAuth,
    OAuthError,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])

_STATE_PURPOSE = "oauth_state"
_STATE_TTL = timedelta(minutes=10)


def _redirect_uri(settings: Settings) -> str:
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/integrations/google/callback"


def _require_google(settings: Settings) -> GoogleOAuth:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured (set GOOGLE_CLIENT_ID/SECRET).",
        )
    return GoogleOAuth(settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET)


def _mint_state(user_id: str, secret: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id,
            "purpose": _STATE_PURPOSE,
            "iat": int(now.timestamp()),
            "exp": int((now + _STATE_TTL).timestamp()),
        },
        secret,
        algorithm="HS256",
    )


def _verify_state(state: str, secret: str) -> str:
    try:
        claims = jwt.decode(state, secret, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=400, detail="invalid or expired state") from exc
    if claims.get("purpose") != _STATE_PURPOSE or not claims.get("sub"):
        raise HTTPException(status_code=400, detail="invalid state")
    return str(claims["sub"])


def _pool(request: Request) -> Any:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="database unavailable")
    return pool


def _start_consent(token: str, scopes: list[str]) -> RedirectResponse:
    """Authenticate the user with our JWT and redirect to Google consent for ``scopes``."""
    settings = get_settings()
    try:
        user = verify_access_token(token, secret=settings.JWT_SECRET)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    oauth = _require_google(settings)
    url = oauth.build_auth_url(
        redirect_uri=_redirect_uri(settings),
        scopes=scopes,
        state=_mint_state(user.id, settings.JWT_SECRET),
    )
    return RedirectResponse(url)


@router.get("/google/gmail/connect")
async def gmail_connect(token: str) -> RedirectResponse:
    """Start Gmail consent. ``token`` is the user's access JWT (query for browser use)."""
    return _start_consent(token, [GMAIL_READONLY_SCOPE])


@router.get("/google/calendar/connect")
async def calendar_connect(token: str) -> RedirectResponse:
    """Start Google Calendar consent (incremental — adds to any existing grant)."""
    return _start_consent(token, [CALENDAR_READONLY_SCOPE])


@router.get("/google/callback")
async def google_callback(
    request: Request, state: str, code: str | None = None, error: str | None = None
) -> HTMLResponse:
    """Google redirects here after consent; store the encrypted grant."""
    settings = get_settings()
    if error:
        return _page(f"Connection cancelled ({error}). You can close this tab.")
    if not code:
        raise HTTPException(status_code=400, detail="missing code")
    user_id = _verify_state(state, settings.JWT_SECRET)
    oauth = _require_google(settings)
    try:
        tokens = await oauth.exchange_code(code, _redirect_uri(settings))
        info = await oauth.fetch_userinfo(tokens.access_token)
    except OAuthError as exc:
        raise HTTPException(status_code=502, detail=f"Google OAuth failed: {exc}") from exc

    key = load_key(settings)
    expiry = datetime.now(UTC) + timedelta(seconds=tokens.expires_in)
    async with _pool(request).acquire() as conn:
        await repo.upsert_provider_account(
            conn,
            user_id=user_id,
            provider="google",
            provider_subject=str(info.get("sub", user_id)),
            email=info.get("email"),
            scopes=tokens.scope or GMAIL_READONLY_SCOPE,
            access_token_enc=encrypt(tokens.access_token, key),
            refresh_token_enc=encrypt(tokens.refresh_token, key) if tokens.refresh_token else None,
            token_expiry=expiry,
        )
    return _page("Gmail connected ✓ — you can close this tab and talk to EDITH.")


def _page(message: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><body style='font-family:sans-serif;padding:3rem'>"
        f"<h2>EDITH</h2><p>{message}</p></body></html>"
    )
