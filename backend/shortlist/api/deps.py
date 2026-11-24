# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI dependencies for database sessions, authentication, CSRF, and RBAC."""

from __future__ import annotations

import hmac
from collections.abc import Callable, Generator
from typing import cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from shortlist.api.auth import (
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    decode_session_token,
)
from shortlist.config import Settings, get_settings
from shortlist.db.models import User
from shortlist.db.session import get_session_factory
from shortlist.schemas.common import UserRole

_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def get_app_settings(request: Request) -> Settings:
    """Return Settings from app.state if overridden, else global cached settings."""
    state_settings = getattr(request.app.state, "settings", None)
    if isinstance(state_settings, Settings):
        return state_settings
    return get_settings()


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """Yield a scoped SQLAlchemy session using app.state.session_factory if configured."""
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        factory = get_session_factory()
    session_factory = cast(sessionmaker[Session], factory)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> User:
    """Authenticate the current user from the httpOnly session cookie and enforce CSRF."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    claims = decode_session_token(token, settings.secret_key)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
        )

    if request.method in _STATE_CHANGING_METHODS:
        csrf_header = request.headers.get(CSRF_HEADER_NAME, "")
        expected_csrf = str(claims["csrf"])
        if not csrf_header or not hmac.compare_digest(csrf_header, expected_csrf):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing CSRF token.",
            )

    user = db.get(User, str(claims["uid"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found.",
        )
    return user


def require_roles(*allowed_roles: UserRole) -> Callable[[User], User]:
    """Return a dependency that enforces the authenticated user has one of allowed_roles."""
    allowed = {role.value for role in allowed_roles}

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action.",
            )
        return user

    return _checker
