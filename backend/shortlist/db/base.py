# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""SQLAlchemy declarative base and shared column helpers."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


def new_uuid() -> str:
    """Generate a new UUID4 string primary key."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for all Shortlist ORM models."""
