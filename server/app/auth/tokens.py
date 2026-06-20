"""Token primitives: our session JWTs + opaque refresh tokens.

Pure functions, no I/O — unit-testable without a database. We mint **our own**
access JWTs (HS256 over ``JWT_SECRET``); the WebSocket and any future HTTP API
verify these. Refresh tokens are opaque high-entropy strings; only their SHA-256
hash is ever stored (``refresh_tokens.token_hash``), so a DB leak can't be replayed.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"


class AuthError(Exception):
    """Raised when a token or credential cannot be verified."""


@dataclass(frozen=True)
class AuthedUser:
    """The authenticated principal for a connection."""

    id: str
    display_name: str


def mint_access_token(
    *,
    user_id: str,
    display_name: str,
    secret: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> str:
    """Mint a short-lived access JWT for ``user_id``."""
    issued = now or datetime.now(UTC)
    payload = {
        "sub": user_id,
        "name": display_name,
        "typ": ACCESS_TOKEN_TYPE,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_access_token(token: str, *, secret: str) -> AuthedUser:
    """Verify an access JWT and return the principal. Raises :class:`AuthError`."""
    if not token:
        raise AuthError("missing token")
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("invalid token") from exc
    if claims.get("typ") != ACCESS_TOKEN_TYPE:
        raise AuthError("wrong token type")
    sub = claims.get("sub")
    if not sub:
        raise AuthError("token missing subject")
    return AuthedUser(id=str(sub), display_name=str(claims.get("name", "")))


def generate_refresh_token() -> tuple[str, str]:
    """Return ``(raw_token, token_hash)``. Store only the hash; return raw to client."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    """SHA-256 hex of a refresh token. Deterministic — used for lookup + storage."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
