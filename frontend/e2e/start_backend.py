# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""E2E test backend launcher: temp SQLite DB + FastAPI + WorkerRunner with SHORTLIST_FAKE_LLM=1."""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

import uvicorn

# Create an isolated temporary directory for DB and uploaded CV files
_TMP_DIR = Path(tempfile.mkdtemp(prefix="shortlist_e2e_"))
_DB_PATH = _TMP_DIR / "e2e.db"
_FILES_DIR = _TMP_DIR / "files"
_FILES_DIR.mkdir(parents=True, exist_ok=True)

os.environ["SHORTLIST_FAKE_LLM"] = "1"
os.environ["SHORTLIST_DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"
os.environ["SHORTLIST_FILES_DIR"] = str(_FILES_DIR)
os.environ["SHORTLIST_SECRET_KEY"] = "e2e-test-secret-key-not-for-production-use"
os.environ["SHORTLIST_ENVIRONMENT"] = "development"

from shortlist.api.app import create_app  # noqa: E402
from shortlist.config import get_settings  # noqa: E402
from shortlist.db.models import Base  # noqa: E402
from shortlist.db.session import create_db_engine, get_session_factory  # noqa: E402
from shortlist.worker.runner import WorkerRunner  # noqa: E402


def main() -> None:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(bind=engine)
    session_factory = get_session_factory(engine)

    stop_event = threading.Event()
    worker = WorkerRunner(
        session_factory,
        secret_key=settings.secret_key,
        poll_interval=0.2,
        force_fake_llm=True,
    )
    worker_thread = threading.Thread(target=worker.run_forever, args=(stop_event,), daemon=True)
    worker_thread.start()

    app = create_app(settings_override=settings, session_factory=session_factory)
    try:
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
    finally:
        stop_event.set()


if __name__ == "__main__":
    main()
