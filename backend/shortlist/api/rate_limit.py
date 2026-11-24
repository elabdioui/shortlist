# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""In-memory sliding-window rate limiter for login attempts."""

from __future__ import annotations

import threading
import time
from collections import deque


class LoginRateLimiter:
    """Sliding-window rate limiter keyed by client identifier (IP / email)."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 60) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, queue: deque[float], now: float) -> None:
        cutoff = now - self._window_seconds
        while queue and queue[0] <= cutoff:
            queue.popleft()

    def check_allowed(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            queue = self._attempts.get(key)
            if queue is None:
                return True, 0
            self._prune(queue, now)
            if len(queue) >= self._max_attempts:
                retry_after = max(1, int(self._window_seconds - (now - queue[0])) + 1)
                return False, retry_after
            return True, 0

    def record_failure(self, key: str) -> None:
        """Record a failed login attempt for the given key."""
        now = time.monotonic()
        with self._lock:
            queue = self._attempts.setdefault(key, deque())
            self._prune(queue, now)
            queue.append(now)

    def reset(self, key: str) -> None:
        """Clear recorded failures after a successful login."""
        with self._lock:
            self._attempts.pop(key, None)
