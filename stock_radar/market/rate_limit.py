import threading
import time
from collections import deque


class SlidingWindowRateLimiter:
    """Thread-safe sliding window: at most max_calls within period_seconds."""

    def __init__(self, max_calls: int = 50, period_seconds: float = 60.0):
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= self.period_seconds:
                    self._timestamps.popleft()
                if len(self._timestamps) < self.max_calls:
                    self._timestamps.append(now)
                    return
                wait = self.period_seconds - (now - self._timestamps[0])
            if wait > 0:
                time.sleep(wait)
