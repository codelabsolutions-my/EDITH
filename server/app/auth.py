"""Authentication for the WebSocket handshake.

**M0 stub:** ``verify_jwt`` accepts any non-empty token and returns a deterministic
fake user id derived from it. This unblocks the whole text-mode agent demo with no
auth backend.

**TODO(M1):** replace with real OIDC relying-party verification — validate the
issuer/audience/signature against cached JWKS and map to the real ``users.id``
(see ``docs/specs/phase-1-auth.md``).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


class AuthError(Exception):
    """Raised when a token cannot be verified."""


@dataclass(frozen=True)
class AuthedUser:
    """The authenticated principal for a connection."""

    id: str
    display_name: str


def verify_jwt(token: str) -> AuthedUser:
    """Verify a WS auth token and return the user. M0: accept any non-empty token."""
    if not token:
        raise AuthError("missing token")
    # Deterministic fake id so the same token maps to the same user across reconnects.
    fake_id = "u_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return AuthedUser(id=fake_id, display_name="Test User")
