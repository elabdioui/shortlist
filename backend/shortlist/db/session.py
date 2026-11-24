# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Database engine and session management (SQLite WAL & PostgreSQL)."""

from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from shortlist.config import get_settings


def _configure_sqlite(dbapi_connection: Any, _connection_record: Any) -> None:
    """Enable WAL mode and foreign key constraints for SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


def create_db_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured database URL."""
    url = database_url or get_settings().database_url
    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Ensure parent directory exists for file-backed SQLite databases.
        if url.startswith("sqlite:///") and not url.endswith(":memory:"):
            db_path = Path(url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite)
    return engine


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Return a configured sessionmaker bound to the given or default engine."""
    bound_engine = engine or create_db_engine()
    return sessionmaker(
        bind=bound_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
