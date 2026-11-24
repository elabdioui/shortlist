# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Concurrent, crash-resumable worker runner polling the DB task queue."""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from shortlist.worker.queue import (
    claim_next_task,
    process_task,
    reconcile_active_runs,
    recover_stale_tasks,
)

logger = logging.getLogger("shortlist.worker.runner")

_DEFAULT_CONCURRENCY = 4


def _run_with_sqlite_retry[T](fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Retry a callable briefly if SQLite reports 'database is locked'."""
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < 4:
                time.sleep(0.05 * (attempt + 1))
                continue
            raise
    raise RuntimeError("Unreachable")


class WorkerRunner:
    """Polls AnalysisTask rows, leases them atomically, and executes CV evaluations."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        secret_key: str,
        concurrency: int | None = None,
        poll_interval: float = 0.5,
        lease_seconds: int = 120,
        force_fake_llm: bool = False,
        worker_id: str | None = None,
    ) -> None:
        env_conc = os.environ.get("SHORTLIST_WORKER_CONCURRENCY", "")
        resolved_conc = concurrency or (
            int(env_conc) if env_conc.isdigit() else _DEFAULT_CONCURRENCY
        )
        self.session_factory = session_factory
        self.secret_key = secret_key
        self.concurrency = max(1, resolved_conc)
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self.force_fake_llm = force_fake_llm
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"

    def recover_stale(self) -> int:
        """Recover expired task leases on startup or between polling cycles."""
        with self.session_factory() as db:
            recovered = _run_with_sqlite_retry(recover_stale_tasks, db)
        if recovered:
            logger.info("Recovered %d stale leased task(s).", recovered)
        return recovered

    def _execute_task(self, task_id: str) -> None:
        with self.session_factory() as db:
            _run_with_sqlite_retry(
                process_task,
                db,
                task_id,
                secret_key=self.secret_key,
                force_fake_llm=self.force_fake_llm,
            )

    def _claim_one(self) -> str | None:
        with self.session_factory() as db:
            res = _run_with_sqlite_retry(
                claim_next_task,
                db,
                self.worker_id,
                lease_seconds=self.lease_seconds,
            )
            return str(res) if res is not None else None

    def run_once(self, max_tasks: int | None = None) -> int:
        """Claim up to `concurrency` (or `max_tasks`) tasks and process them."""
        limit = self.concurrency if max_tasks is None else min(self.concurrency, max_tasks)
        claimed: list[str] = []
        for _ in range(limit):
            task_id = self._claim_one()
            if task_id is None:
                break
            claimed.append(task_id)

        if not claimed:
            return 0

        if len(claimed) == 1 or self.concurrency == 1:
            for tid in claimed:
                self._execute_task(tid)
            return len(claimed)

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures: list[Future[None]] = [
                executor.submit(self._execute_task, tid) for tid in claimed
            ]
            for fut in futures:
                fut.result()

        with self.session_factory() as db:
            _run_with_sqlite_retry(reconcile_active_runs, db)

        return len(claimed)

    def run_until_idle(self, max_tasks: int | None = None) -> int:
        """Recover stale leases and process tasks until queue is empty or max_tasks reached."""
        self.recover_stale()
        total_processed = 0
        while True:
            remaining = None if max_tasks is None else max(0, max_tasks - total_processed)
            if remaining == 0:
                break
            count = self.run_once(max_tasks=remaining)
            if count == 0:
                break
            total_processed += count
        return total_processed

    def run_forever(self, stop_event: threading.Event) -> None:
        """Continuously poll for tasks until stop_event is set."""
        self.recover_stale()
        last_recovery = time.monotonic()

        while not stop_event.is_set():
            processed = self.run_once()
            now = time.monotonic()
            if now - last_recovery >= 30.0:
                self.recover_stale()
                last_recovery = now
            if processed == 0:
                stop_event.wait(timeout=self.poll_interval)
