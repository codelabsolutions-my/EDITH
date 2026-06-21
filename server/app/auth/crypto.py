"""Authenticated encryption for OAuth tokens at rest (AES-256-GCM).

Provider API tokens live in ``provider_accounts.access_token_enc`` /
``refresh_token_enc`` as ciphertext, never plaintext. We use AES-GCM (authenticated)
with the 32-byte key in ``TOKEN_ENCRYPTION_KEY`` (base64). The stored blob is
``nonce(12) || ciphertext||tag`` — self-contained, so rotation only needs the key.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import Settings

_NONCE_BYTES = 12


class TokenCryptoError(Exception):
    """Raised when the encryption key is missing/invalid or decryption fails."""


def load_key(settings: Settings) -> bytes:
    """Decode and validate the 32-byte AES key from settings."""
    raw = settings.TOKEN_ENCRYPTION_KEY
    if not raw:
        raise TokenCryptoError("TOKEN_ENCRYPTION_KEY is not set")
    try:
        key = base64.b64decode(raw)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise TokenCryptoError("TOKEN_ENCRYPTION_KEY is not valid base64") from exc
    if len(key) != 32:
        raise TokenCryptoError("TOKEN_ENCRYPTION_KEY must decode to 32 bytes (AES-256)")
    return key


def encrypt(plaintext: str, key: bytes) -> bytes:
    """Encrypt ``plaintext`` → ``nonce || ciphertext`` (AES-256-GCM)."""
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt(blob: bytes, key: bytes) -> str:
    """Decrypt a ``nonce || ciphertext`` blob. Raises on tamper/bad key."""
    if len(blob) <= _NONCE_BYTES:
        raise TokenCryptoError("ciphertext too short")
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception as exc:  # cryptography raises InvalidTag etc.
        raise TokenCryptoError("could not decrypt token") from exc
