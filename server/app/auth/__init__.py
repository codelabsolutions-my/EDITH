"""Auth package: OIDC relying party (seam) + our own JWT sessions.

Public surface used elsewhere:
- :func:`verify_jwt` / :class:`AuthError` / :class:`AuthedUser` — the WebSocket
  handshake (``ws.py``) verifies our access JWT with these.
- :class:`AuthService` — the HTTP auth routes mint/rotate/revoke sessions.
- :data:`router` — the ``/auth/*`` FastAPI routes.
"""

from __future__ import annotations

from ..config import get_settings
from .router import router
from .service import AuthService, SessionTokens
from .tokens import AuthedUser, AuthError, verify_access_token

__all__ = [
    "AuthError",
    "AuthService",
    "AuthedUser",
    "SessionTokens",
    "router",
    "verify_jwt",
]


def verify_jwt(token: str) -> AuthedUser:
    """Verify a WS access token against the configured ``JWT_SECRET``.

    Thin wrapper over :func:`verify_access_token` that pulls the process-wide
    settings, so the WebSocket handshake can stay a one-argument call.
    """
    return verify_access_token(token, secret=get_settings().JWT_SECRET)
