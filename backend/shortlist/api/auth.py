# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Argon2 password hashing, signed httpOnly session cookies, CSRF tokens, and audit logging."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.orm import Session

from shortlist.db.models import AuditLog

SESSION_COOKIE_NAME = "shortlist_session"
CSRF_COOKIE_NAME = "shortlist_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
DEFAULT_SESSION_TTL_SECONDS = 7 * 24 * 3600

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a plaintext password against an Argon2 hash."""
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def generate_csrf_token() -> str:
    """Generate a cryptographically random URL-safe CSRF token."""
    return secrets.token_urlsafe(32)


def _sign_payload(encoded_payload: str, secret_key: str) -> str:
    mac = hmac.new(
        secret_key.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")


def create_session_token(
    user_id: str,
    role: str,
    csrf_token: str,
    secret_key: str,
    *,
    ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
) -> str:
    """Create a signed session cookie token."""
    payload = {
        "uid": user_id,
        "role": role,
        "csrf": csrf_token,
        "exp": int(time.time()) + ttl_seconds,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = _sign_payload(encoded, secret_key)
    return f"{encoded}.{sig}"


def decode_session_token(token: str, secret_key: str) -> dict[str, Any] | None:
    """Verify signature and expiration of a session token, returning claims or None."""
    if "." not in token:
        return None
    encoded, sig = token.split(".", 1)
    expected_sig = _sign_payload(encoded, secret_key)
    if not hmac.compare_digest(sig, expected_sig):
        return None

    padding = "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode(encoded + padding)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    exp = data.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        return None
    if not isinstance(data.get("uid"), str) or not isinstance(data.get("csrf"), str):
        return None
    return data


def record_audit(
    db: Session,
    user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append an entry to the audit_log table."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
    )
    db.add(entry)
