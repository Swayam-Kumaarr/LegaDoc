"""In-memory sliding window rate limiter for sensitive endpoints.

See SYSTEM_DESIGN.md Flow 6 and row 705:
GET /cases/:id/audit-log/ai-parser is rate-limited separately (20/min per user)
from the general API default.
"""

import threading
import time
from collections import defaultdict
from fastapi import HTTPException, status


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window rate limiter with TTL eviction."""

    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, detail: str | None = None) -> None:
        """Checks whether the given key has exceeded the allowed request quota.
        Raises HTTPException(429) with Retry-After header if exceeded.
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # Evict timestamps outside current sliding window
            timestamps = [t for t in self._requests[key] if t > cutoff]
            if len(timestamps) >= self.max_requests:
                earliest_active = timestamps[0]
                retry_after = max(1, int(earliest_active + self.window_seconds - now) + 1)
                err_detail = detail or f"Rate limit exceeded. Maximum {self.max_requests} requests per {self.window_seconds}s."
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=err_detail,
                    headers={"Retry-After": str(retry_after)},
                )

            timestamps.append(now)
            self._requests[key] = timestamps

            # Periodic memory cleanup: evict stale keys
            stale_keys = [k for k, v in self._requests.items() if not v or v[-1] <= cutoff]
            for sk in stale_keys:
                del self._requests[sk]

    def reset(self) -> None:
        """Resets all tracking state (used in automated test fixtures)."""
        with self._lock:
            self._requests.clear()


# Default singleton instance for AI Parser audit endpoint (20 req / 60 sec)
ai_parser_limiter = SlidingWindowRateLimiter(max_requests=20, window_seconds=60)

# Default singleton instance for Login endpoint (10 req / 60 sec per IP, see settings.LOGIN_RATE_LIMIT)
login_rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)
