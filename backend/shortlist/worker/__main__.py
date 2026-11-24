# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Worker process entrypoint (`python -m shortlist.worker`)."""

from __future__ import annotations

import logging
import signal
import threading
from types import FrameType

from shortlist.config import get_settings
from shortlist.db.session import get_session_factory
from shortlist.worker.runner import WorkerRunner

logger = logging.getLogger("shortlist.worker")


def main() -> None:
    """Run the Shortlist persistent worker polling loop."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    stop_event = threading.Event()

    def _handle_signal(_signum: int, _frame: FrameType | None) -> None:
        logger.info("Shutdown signal received; stopping worker.")
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    session_factory = get_session_factory()
    runner = WorkerRunner(session_factory, secret_key=settings.secret_key)

    logger.info(
        "Shortlist worker v%s started (env=%s, concurrency=%d, worker_id=%s)",
        settings.version,
        settings.environment,
        runner.concurrency,
        runner.worker_id,
    )
    runner.run_forever(stop_event)


if __name__ == "__main__":
    main()
