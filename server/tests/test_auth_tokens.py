"""Unit tests for the token primitives — no DB, no network."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.auth.tokens import (
    AuthError,
    generate_refresh_token,
    hash_refresh_token,
    mint_access_token,
    verify_access_token,
)

SECRET = "unit-test-secret-0123456789abcdef-long-enough"


def test_mint_then_verify_roundtrip() -> None:
    token = mint_access_token(user_id="user-1", display_name="Ali", secret=SECRET, ttl_seconds=900)
    user = verify_access_token(token, secret=SECRET)
    assert user.id == "user-1"
    assert user.display_name == "Ali"


def test_empty_token_rejected() -> None:
    with pytest.raises(AuthError):
        verify_access_token("", secret=SECRET)


def test_wrong_secret_rejected() -> None:
    token = mint_access_token(user_id="u", display_name="", secret=SECRET, ttl_seconds=900)
    with pytest.raises(AuthError):
        verify_access_token(token, secret="different-secret")


def test_expired_token_rejected() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    token = mint_access_token(user_id="u", display_name="", secret=SECRET, ttl_seconds=60, now=past)
    with pytest.raises(AuthError):
        verify_access_token(token, secret=SECRET)


def test_wrong_token_type_rejected() -> None:
    # A token without our access "typ" claim must not pass.
    forged = jwt.encode({"sub": "u", "typ": "refresh"}, SECRET, algorithm="HS256")
    with pytest.raises(AuthError):
        verify_access_token(forged, secret=SECRET)


def test_token_without_subject_rejected() -> None:
    forged = jwt.encode({"typ": "access"}, SECRET, algorithm="HS256")
    with pytest.raises(AuthError):
        verify_access_token(forged, secret=SECRET)


def test_refresh_token_hash_is_deterministic_and_opaque() -> None:
    raw, digest = generate_refresh_token()
    assert raw != digest
    assert hash_refresh_token(raw) == digest
    # Two generated tokens differ.
    raw2, _ = generate_refresh_token()
    assert raw2 != raw
