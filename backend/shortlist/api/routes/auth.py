# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Authentication, first-launch setup, session cookies, and user management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shortlist.api.auth import (
    CSRF_COOKIE_NAME,
    DEFAULT_SESSION_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    create_session_token,
    decode_session_token,
    generate_csrf_token,
    hash_password,
    record_audit,
    verify_password,
)
from shortlist.api.deps import get_app_settings, get_current_user, get_db_session, require_roles
from shortlist.api.rate_limit import LoginRateLimiter
from shortlist.api.schemas import (
    AuthSessionResponse,
    AuthSetupRequest,
    SetupStatusResponse,
    UserUpdate,
)
from shortlist.config import Settings
from shortlist.db.models import User
from shortlist.schemas.common import UserRole
from shortlist.schemas.users import LoginRequest, UserCreate, UserResponse

router = APIRouter(tags=["auth"])

_default_limiter = LoginRateLimiter(max_attempts=5, window_seconds=60)


def _get_limiter(request: Request) -> LoginRateLimiter:
    limiter = getattr(request.app.state, "login_limiter", None)
    if isinstance(limiter, LoginRateLimiter):
        return limiter
    return _default_limiter


def _set_session_cookies(
    response: Response,
    user: User,
    settings: Settings,
) -> str:
    csrf_token = generate_csrf_token()
    token = create_session_token(user.id, user.role, csrf_token, settings.secret_key)
    secure = settings.environment == "production"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=DEFAULT_SESSION_TTL_SECONDS,
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=DEFAULT_SESSION_TTL_SECONDS,
    )
    return csrf_token


@router.get("/api/auth/status", response_model=SetupStatusResponse)
def auth_status(db: Session = Depends(get_db_session)) -> SetupStatusResponse:
    """Return whether initial admin setup is still required."""
    user_count = int(db.scalar(select(func.count(User.id))) or 0)
    return SetupStatusResponse(needs_setup=user_count == 0)


@router.post(
    "/api/auth/setup",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def setup_first_admin(
    payload: AuthSetupRequest,
    response: Response,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthSessionResponse:
    """Create the initial admin account when no users exist yet."""
    user_count = int(db.scalar(select(func.count(User.id))) or 0)
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Initial setup has already been completed.",
        )

    admin = User(
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        role=UserRole.ADMIN.value,
        locale=payload.locale,
    )
    db.add(admin)
    db.flush()
    record_audit(db, admin.id, "auth.setup", "user", admin.id, {"email": admin.email})
    db.commit()
    db.refresh(admin)

    csrf_token = _set_session_cookies(response, admin, settings)
    return AuthSessionResponse(user=UserResponse.model_validate(admin), csrf_token=csrf_token)


@router.post("/api/auth/login", response_model=AuthSessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthSessionResponse:
    """Authenticate with email and password, issuing an httpOnly session cookie."""
    client_ip = request.client.host if request.client else "unknown"
    email = payload.email.strip().lower()
    rate_key = f"{client_ip}:{email}"
    limiter = _get_limiter(request)

    allowed, retry_after = limiter.check_allowed(rate_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please retry later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(user.password_hash, payload.password):
        limiter.record_failure(rate_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    limiter.reset(rate_key)
    record_audit(db, user.id, "auth.login", "user", user.id)
    db.commit()

    csrf_token = _set_session_cookies(response, user, settings)
    return AuthSessionResponse(user=UserResponse.model_validate(user), csrf_token=csrf_token)


@router.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    _user: User = Depends(get_current_user),
) -> None:
    """Clear the session and CSRF cookies."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


@router.get("/api/auth/me", response_model=AuthSessionResponse)
def me(
    request: Request,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_app_settings),
) -> AuthSessionResponse:
    """Return the currently authenticated user and CSRF token."""
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    claims = decode_session_token(token, settings.secret_key) or {}
    csrf_token = str(claims.get("csrf", ""))
    return AuthSessionResponse(user=UserResponse.model_validate(user), csrf_token=csrf_token)


@router.get("/api/users", response_model=list[UserResponse])
def list_users(
    _admin: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
) -> list[UserResponse]:
    """List all user accounts (admin only)."""
    users = db.scalars(select(User).order_by(User.created_at.asc())).all()
    return [UserResponse.model_validate(u) for u in users]


@router.post(
    "/api/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
) -> UserResponse:
    """Create a new user account (admin only)."""
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        locale=payload.locale,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        admin.id,
        "user.create",
        "user",
        user.id,
        {"email": user.email, "role": user.role},
    )
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.patch("/api/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    payload: UserUpdate,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
) -> UserResponse:
    """Update a user's role or locale (admin only)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if payload.role is not None:
        user.role = payload.role.value
    if payload.locale is not None:
        user.locale = payload.locale

    record_audit(db, admin.id, "user.update", "user", user.id)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
) -> None:
    """Delete a user account (admin only; cannot delete self)."""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own admin account.",
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    record_audit(db, admin.id, "user.delete", "user", user.id, {"email": user.email})
    db.delete(user)
    db.commit()
