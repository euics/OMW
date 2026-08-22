from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Callable


class SlidingWindowRateLimiter:
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("rate limit and window must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = self._clock()
        threshold = now - self.window_seconds

        with self._lock:
            requests = self._requests[key]
            while requests and requests[0] <= threshold:
                requests.popleft()

            if len(requests) >= self.limit:
                retry_after = max(1, int(requests[0] + self.window_seconds - now) + 1)
                return False, retry_after

            requests.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()