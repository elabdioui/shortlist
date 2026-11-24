# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fernet encryption, decryption, and masking for provider API keys."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet


def _derive_fernet_key(secret_key: str) -> bytes:
    """Derive a valid 32-byte urlsafe-base64 Fernet key from SHORTLIST_SECRET_KEY."""
    if not secret_key:
        raise ValueError("SHORTLIST_SECRET_KEY must not be empty.")
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(raw_secret: str, secret_key: str) -> str:
    """Encrypt a raw API key secret using Fernet."""
    fernet = Fernet(_derive_fernet_key(secret_key))
    return fernet.encrypt(raw_secret.encode("utf-8")).decode("ascii")


def decrypt_secret(encrypted_secret: str, secret_key: str) -> str:
    """Decrypt a Fernet-encrypted API key secret."""
    fernet = Fernet(_derive_fernet_key(secret_key))
    return fernet.decrypt(encrypted_secret.encode("ascii")).decode("utf-8")


def mask_secret(raw_secret: str) -> str:
    """Return a masked display string (e.g. 'AIza...x9F2'), never exposing the full secret."""
    stripped = raw_secret.strip()
    if len(stripped) <= 8:
        return "****"
    return f"{stripped[:4]}...{stripped[-4:]}"
