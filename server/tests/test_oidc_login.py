"""Google OIDC login: id_token verification + sign-in flow (RSA-signed mocks)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg
import jwt
import pytest
from app.auth.oidc import GOOGLE_ISSUERS, OidcIdentity, verify_id_token
from app.auth.tokens import AuthError
from app.config import Settings, get_settings, reset_settings_cache
from app.main import create_app
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from tests.conftest import TEST_DATABASE_URL, reset_db

# One RSA keypair for the whole module (keygen is slow).
_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUB = _PRIV.public_key()
AUD = "edith-web.apps.googleusercontent.com"


class FakeResolver:
    """Returns our test public key regardless of the JWKS URL."""

    def __init__(self, url: str | None = None) -> None:
        pass

    def key_for(self, token: str) -> object:
        return _PUB


def _id_token(**overrides) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": GOOGLE_ISSUERS[0],
        "aud": AUD,
        "sub": "google-sub-123",
        "email": "ian@gmail.com",
        "email_verified": True,
        "name": "Ian",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    claims.update(overrides)
    return jwt.encode(claims, _PRIV, algorithm="RS256")


def _settings() -> Settings:
    return Settings(GOOGLE_CLIENT_ID=AUD)


def test_verify_valid_google_id_token() -> None:
    identity = asyncio.run(
        verify_id_token("google", _id_token(), _settings(), key_resolver=FakeResolver())
    )
    assert isinstance(identity, OidcIdentity)
    assert identity.subject == "google-sub-123"
    assert identity.email == "ian@gmail.com"
    assert identity.name == "Ian"


def test_unverified_email_is_dropped() -> None:
    identity = asyncio.run(
        verify_id_token(
            "google", _id_token(email_verified=False), _settings(), key_resolver=FakeResolver()
        )
    )
    assert identity.email is None  # not trusted for linking


def test_wrong_audience_rejected() -> None:
    with pytest.raises(AuthError):
        asyncio.run(
            verify_id_token(
                "google", _id_token(aud="someone-else"), _settings(), key_resolver=FakeResolver()
            )
        )


def test_expired_token_rejected() -> None:
    past = datetime.now(UTC) - timedelta(hours=2)
    tok = _id_token(exp=int(past.timestamp()), iat=int((past - timedelta(hours=1)).timestamp()))
    with pytest.raises(AuthError):
        asyncio.run(verify_id_token("google", tok, _settings(), key_resolver=FakeResolver()))


def test_unconfigured_google_fails_closed() -> None:
    with pytest.raises(AuthError):
        asyncio.run(
            verify_id_token(
                "google", _id_token(), Settings(GOOGLE_CLIENT_ID=""), key_resolver=FakeResolver()
            )
        )


def test_unsupported_provider_rejected() -> None:
    with pytest.raises(AuthError):
        asyncio.run(verify_id_token("facebook", "x", _settings(), key_resolver=FakeResolver()))


@pytest.fixture
def google_login_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", AUD)
    monkeypatch.setattr("app.auth.oidc.SigningKeyResolver", FakeResolver)
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_google_login_creates_user_and_is_idempotent(pg_dsn: str, google_login_env) -> None:
    async def _reset() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=2)
        assert pool is not None
        await reset_db(pool)
        await pool.close()

    asyncio.run(_reset())

    app = create_app()
    with TestClient(app) as client:
        r1 = client.post("/auth/google", json={"id_token": _id_token()})
        assert r1.status_code == 200, r1.text
        first = r1.json()
        assert first["user"]["primary_email"] == "ian@gmail.com"
        assert first["access_token"] and first["refresh_token"]

        # Logging in again maps to the SAME user (by IdP subject).
        r2 = client.post("/auth/google", json={"id_token": _id_token()})
        assert r2.json()["user"]["id"] == first["user"]["id"]

    async def _count_users() -> int:
        conn = await asyncpg.connect(TEST_DATABASE_URL)
        try:
            return await conn.fetchval("SELECT count(*) FROM users")
        finally:
            await conn.close()

    assert asyncio.run(_count_users()) == 1


def test_login_does_not_wipe_existing_api_grant(pg_dsn: str, google_login_env) -> None:
    """Signing in must preserve a previously connected Gmail/Calendar token grant."""

    async def scenario() -> bytes | None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=2)
        assert pool is not None
        try:
            await reset_db(pool)
            # Pre-seed a user with a google account carrying an API token + scopes.
            uid = await pool.fetchval(
                "INSERT INTO users (primary_email) VALUES ('ian@gmail.com') RETURNING id"
            )
            await pool.execute(
                """INSERT INTO provider_accounts
                   (user_id, provider, provider_subject, email, scopes, access_token_enc)
                   VALUES ($1,'google','google-sub-123','ian@gmail.com','gmail.readonly',$2)""",
                uid,
                b"existing-ciphertext",
            )
            from app.auth.service import AuthService

            svc = AuthService(pool, get_settings())
            await svc.login_from_identity(
                provider="google", subject="google-sub-123", email="ian@gmail.com", name="Ian"
            )
            row = await pool.fetchrow(
                "SELECT access_token_enc, scopes FROM provider_accounts WHERE user_id = $1", uid
            )
            assert row["scopes"] == "gmail.readonly"  # not wiped
            return row["access_token_enc"]
        finally:
            await pool.close()

    assert bytes(asyncio.run(scenario())) == b"existing-ciphertext"
