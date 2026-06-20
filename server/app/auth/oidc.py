"""OIDC relying-party verification seam (Google / Microsoft / Apple).

Phase 1 is **login-only**: verify a provider ``id_token`` (issuer, audience,
signature via the provider's JWKS), then map ``sub`` + ``email`` to our ``users``
row. The verification contract lives here; the live JWKS clients land when the
relying-party client IDs/secrets are provisioned (``GOOGLE_CLIENT_ID`` etc.).

Until then :func:`verify_id_token` raises :class:`AuthError` so the ``/auth/{provider}``
route fails closed rather than trusting an unverified token. The local
``/auth/dev-login`` path (non-production only) exists so the full stack is runnable
and testable without external provider credentials.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tokens import AuthError

SUPPORTED_PROVIDERS = ("google", "microsoft", "apple")


@dataclass(frozen=True)
class OidcIdentity:
    """The verified identity extracted from a provider ``id_token``."""

    provider: str
    subject: str
    email: str | None
    name: str | None


async def verify_id_token(provider: str, id_token: str) -> OidcIdentity:
    """Verify a provider ``id_token`` and return the identity.

    **Not yet configured.** Raises :class:`AuthError` until relying-party JWKS
    verification is wired (issuer/audience/signature per provider). The seam is
    here so wiring a provider is additive, not surgical.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise AuthError(f"unsupported provider: {provider}")
    raise AuthError(
        f"OIDC provider '{provider}' is not configured on this deployment "
        "(no relying-party credentials). Use /auth/dev-login in development."
    )
