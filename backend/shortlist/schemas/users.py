# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""User authentication and account schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from shortlist.schemas.common import UserRole


class UserCreate(BaseModel):
    """Payload to create a new user."""

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.RECRUITER
    locale: str = Field(default="fr", pattern="^(fr|en|ar)$")


class UserResponse(BaseModel):
    """Public user representation (never includes password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: UserRole
    locale: str
    created_at: datetime


class LoginRequest(BaseModel):
    """Credentials for session login."""

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)
