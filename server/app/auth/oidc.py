"""OIDC relying-party verification (Google login).

Phase 1 is **login-only**: the client signs in with the provider's native SDK,
gets an ``id_token``, and POSTs it to ``/auth/{provider}``; we verify it and map the
identity to our ``users`` row. Verification = signature (provider JWKS, RS256),
issuer, audience (our client IDs — web + mobile), and expiry.

Google is implemented. Microsoft and Apple use the *same* shape (different JWKS,
issuer, audience) and are wired the same way once their client credentials exist;
until then they fail closed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import jwt

from ..config import Settings
from .tokens import AuthError

SUPPORTED_PROVIDERS = ("google", "microsoft", "apple")

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


@dataclass(frozen=True)
class OidcIdentity:
    """The verified identity extracted from a provider ``id_token``."""

    provider: str
    subject: str
    email: str | None
    name: str | None


class SigningKeyResolver:
    """Resolves the signing key for a JWT from a provider's JWKS (override in tests)."""

    def __init__(self, jwks_url: str) -> None:
        self._client = jwt.PyJWKClient(jwks_url)

    def key_for(self, token: str) -> Any:
        return self._client.get_signing_key_from_jwt(token).key


async def verify_id_token(
    provider: str,
    id_token: str,
    settings: Settings,
    *,
    key_resolver: SigningKeyResolver | None = None,
) -> OidcIdentity:
    """Verify a provider ``id_token`` and return the identity. Raises :class:`AuthError`."""
    if provider not in SUPPORTED_PROVIDERS:
        raise AuthError(f"unsupported provider: {provider}")
    if provider != "google":
        raise AuthError(f"OIDC provider '{provider}' is not configured yet (Google is supported).")
    if not settings.google_audiences:
        raise AuthError("Google login is not configured (set GOOGLE_CLIENT_ID).")

    resolver = key_resolver or SigningKeyResolver(GOOGLE_CERTS_URL)
    # JWKS fetch + RSA verify are blocking; keep them off the event loop.
    return await asyncio.to_thread(_verify_google, id_token, settings, resolver)


def _verify_google(id_token: str, settings: Settings, resolver: SigningKeyResolver) -> OidcIdentity:
    try:
        key = resolver.key_for(id_token)
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=settings.google_audiences,
            issuer=list(GOOGLE_ISSUERS),
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid Google id_token: {exc}") from exc
    sub = claims.get("sub")
    if not sub:
        raise AuthError("id_token missing subject")
    # Google sets email_verified; only trust a verified email for account linking.
    email = claims.get("email") if claims.get("email_verified") else None
    return OidcIdentity(
        provider="google",
        subject=str(sub),
        email=email,
        name=claims.get("name"),
    )
