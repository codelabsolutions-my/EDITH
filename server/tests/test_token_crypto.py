"""AES-GCM token encryption: round-trip, tamper detection, key validation."""

from __future__ import annotations

import base64

import pytest
from app.auth.crypto import TokenCryptoError, decrypt, encrypt, load_key
from app.config import Settings

KEY = b"edith-test-key-32-bytes-exactly!"


def test_encrypt_decrypt_roundtrip() -> None:
    blob = encrypt("ya29.secret-access-token", KEY)
    assert blob != b"ya29.secret-access-token"
    assert decrypt(blob, KEY) == "ya29.secret-access-token"


def test_nonce_makes_ciphertext_nondeterministic() -> None:
    assert encrypt("same", KEY) != encrypt("same", KEY)


def test_tampered_ciphertext_is_rejected() -> None:
    blob = bytearray(encrypt("secret", KEY))
    blob[-1] ^= 0x01  # flip a bit in the tag/ciphertext
    with pytest.raises(TokenCryptoError):
        decrypt(bytes(blob), KEY)


def test_wrong_key_is_rejected() -> None:
    blob = encrypt("secret", KEY)
    with pytest.raises(TokenCryptoError):
        decrypt(blob, b"another-32-byte-key-aaaaaaaaaaaa!")


def test_load_key_validates_length() -> None:
    good = Settings(TOKEN_ENCRYPTION_KEY=base64.b64encode(KEY).decode())
    assert load_key(good) == KEY
    with pytest.raises(TokenCryptoError):
        load_key(Settings(TOKEN_ENCRYPTION_KEY=""))
    with pytest.raises(TokenCryptoError):
        load_key(Settings(TOKEN_ENCRYPTION_KEY=base64.b64encode(b"too-short").decode()))
