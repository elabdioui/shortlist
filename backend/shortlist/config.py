# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for Shortlist API, worker, and CLI."""

    model_config = SettingsConfigDict(
        env_prefix="SHORTLIST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Shortlist"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    data_dir: Path = Path("./data")
    database_url: str = "sqlite:///./data/shortlist.db"
    secret_key: str = "dev-insecure-change-me-in-production"

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
