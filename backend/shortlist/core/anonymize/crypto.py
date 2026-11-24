# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fernet encryption/decryption for local PII mapping tables."""

from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet


def _derive_fernet_key(secret_key: str) -> bytes:
    """Derive a valid 32-byte urlsafe-base64 Fernet key from SHORTLIST_SECRET_KEY."""
    if not secret_key:
        raise ValueError("secret_key must not be empty.")
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_pii_map(mapping: dict[str, str], secret_key: str) -> str:
    """Encrypt a placeholder-to-PII dictionary with Fernet."""
    fernet = Fernet(_derive_fernet_key(secret_key))
    payload = json.dumps(mapping, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return fernet.encrypt(payload).decode("ascii")


def decrypt_pii_map(token: str, secret_key: str) -> dict[str, str]:
    """Decrypt a Fernet-encrypted PII mapping table."""
    fernet = Fernet(_derive_fernet_key(secret_key))
    raw = fernet.decrypt(token.encode("ascii"))
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Decrypted PII map is not a JSON object.")
    return {str(k): str(v) for k, v in data.items()}
