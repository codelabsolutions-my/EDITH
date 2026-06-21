"""Device registration for push — ``POST /devices/register``.

Authenticated with our access JWT (Authorization: Bearer). Stores the platform push
token so the proactive scheduler can reach this user's devices.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from .. import repositories as repo
from ..auth.tokens import AuthError, verify_access_token
from ..config import get_settings

router = APIRouter(tags=["devices"])

_ALLOWED_PLATFORMS = {"fcm", "apns", "web"}


class RegisterDeviceRequest(BaseModel):
    platform: str
    token: str


def _current_user_id(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        return verify_access_token(token, secret=get_settings().JWT_SECRET).id
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/devices/register")
async def register_device(
    body: RegisterDeviceRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _current_user_id(authorization)
    if body.platform not in _ALLOWED_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"platform must be one of {_ALLOWED_PLATFORMS}")
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="database unavailable")
    async with pool.acquire() as conn:
        await repo.upsert_device_token(
            conn, user_id=user_id, platform=body.platform, token=body.token
        )
    return {"ok": True}
