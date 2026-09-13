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

    def _prune_locked(self, cutoff: float) -> None:
        """Evict keys whose newest timestamp has aged out. Caller holds the lock."""
        stale_keys = [k for k, v in self._requests.items() if not v or v[-1] <= cutoff]
        for sk in stale_keys:
            del self._requests[sk]

    def peek(self, key: str, detail: str | None = None) -> None:
        """Raises 429 if the key is already over quota, WITHOUT recording an
        attempt.

        Separated from check() so a caller can decide, after doing its own
        work, whether the attempt should count at all. Login uses this: a
        successful sign-in must not consume quota, or ordinary use exhausts
        the budget and locks people out — see routers/auth.py.
        """
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = [t for t in self._requests[key] if t > cutoff]
            self._requests[key] = timestamps
            if len(timestamps) >= self.max_requests:
                retry_after = max(1, int(timestamps[0] + self.window_seconds - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=detail or f"Rate limit exceeded. Maximum {self.max_requests} requests per {self.window_seconds}s.",
                    headers={"Retry-After": str(retry_after)},
                )
            self._prune_locked(cutoff)

    def record(self, key: str) -> None:
        """Counts one attempt against the key without raising."""
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = [t for t in self._requests[key] if t > cutoff]
            timestamps.append(now)
            self._requests[key] = timestamps
            self._prune_locked(cutoff)

    def clear(self, key: str) -> None:
        """Forgets a key's history — used when an attempt succeeds, so a run
        of failures followed by a correct password does not leave the account
        near its limit."""
        with self._lock:
            self._requests.pop(key, None)

    def check(self, key: str, detail: str | None = None) -> None:
        """Peek-then-record in one call: every invocation counts, over-quota
        raises 429. Correct for plain throughput limits (see ai_parser_limiter);
        wrong for login, which must only count failures.
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

            self._prune_locked(cutoff)

    def reset(self) -> None:
        """Resets all tracking state (used in automated test fixtures)."""
        with self._lock:
            self._requests.clear()


# Default singleton instance for AI Parser audit endpoint (20 req / 60 sec)
ai_parser_limiter = SlidingWindowRateLimiter(max_requests=20, window_seconds=60)

# Login limiters. Two buckets, and both count FAILURES ONLY — see
# routers/auth.py.
#
# Keyed per account, because the per-IP key alone was effectively a single
# global bucket: every browser request reaches the API through the Vite dev
# server's /api proxy (see web/vite.config.js), and uvicorn runs without
# --proxy-headers, so request.client.host is the proxy container's address
# for every user. Ten attempts a minute was therefore ten for the entire
# application, shared by everyone, counting successful sign-ins. Walking the
# nine seeded personas exhausted it before anyone typed a wrong password.
login_rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)

# Retained to stop one source spraying many accounts. Higher ceiling because
# this bucket is shared by everyone behind the proxy; it only ever sees
# failures, so ordinary use never approaches it.
login_ip_limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60)
