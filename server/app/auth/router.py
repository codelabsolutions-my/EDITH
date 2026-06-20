"""HTTP auth routes: dev-login (non-prod), refresh, logout.

The OIDC ``/auth/{provider}`` route is present but fails closed until relying-party
credentials are configured (see :mod:`.oidc`). ``/auth/dev-login`` is the
development stand-in that makes the whole stack runnable without a provider.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..config import get_settings
from .oidc import verify_id_token
from .service import AuthService, SessionTokens
from .tokens import AuthError

router = APIRouter(prefix="/auth", tags=["auth"])


class DevLoginRequest(BaseModel):
    email: str
    display_name: str | None = None


class ProviderLoginRequest(BaseModel):
    id_token: str
    display_name: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


def _auth_service(request: Request) -> AuthService:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="database unavailable")
    return AuthService(pool, get_settings())


def _tokens_response(tokens: SessionTokens) -> dict[str, Any]:
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "user": {
            "id": tokens.user_id,
            "display_name": tokens.display_name,
            "primary_email": tokens.primary_email,
        },
    }


@router.post("/dev-login")
async def dev_login(body: DevLoginRequest, request: Request) -> dict[str, Any]:
    """Local development login. Disabled in production."""
    if get_settings().is_production:
        raise HTTPException(status_code=404, detail="not found")
    service = _auth_service(request)
    tokens = await service.dev_login(email=str(body.email), display_name=body.display_name)
    return _tokens_response(tokens)


@router.post("/refresh")
async def refresh(body: RefreshRequest, request: Request) -> dict[str, Any]:
    service = _auth_service(request)
    try:
        tokens = await service.refresh(body.refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return _tokens_response(tokens)


@router.post("/logout")
async def logout(body: LogoutRequest, request: Request) -> dict[str, bool]:
    service = _auth_service(request)
    await service.logout(body.refresh_token)
    return {"ok": True}


# NOTE: the catch-all provider route is declared LAST so it cannot shadow the
# explicit /dev-login, /refresh, /logout paths above.
@router.post("/{provider}")
async def provider_login(
    provider: str, body: ProviderLoginRequest, request: Request
) -> dict[str, Any]:
    """OIDC login. Fails closed until relying-party credentials are configured."""
    try:
        identity = await verify_id_token(provider, body.id_token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    # When OIDC is wired: get-or-create user from identity, then issue tokens.
    service = _auth_service(request)
    tokens = await service.dev_login(
        email=identity.email or "", display_name=identity.name or body.display_name
    )
    return _tokens_response(tokens)
