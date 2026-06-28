"""Global, thread-safe rate limiters for the keyless public APIs.

Why this exists
---------------
iTunes and Deezer are keyless and throttled *per IP address*, not per API
key. The audit pipeline runs many artist threads at once (PARALLEL_ARTISTS
per CSV, and several CSVs simultaneously), so a per-thread ``time.sleep``
cannot bound the *aggregate* request rate — 16 threads each sleeping 0.12s
still produce a combined burst far over the limit.

The fix is a single token bucket per host, shared across ALL threads:
  * ``rate``  tokens are added per second  → the sustained ceiling
  * ``burst`` is the bucket capacity        → the most that can fire at once

``acquire()`` blocks until a token is available, so every caller — no matter
which thread or which CSV it belongs to — is paced against one global budget.

Deezer's documented limit is 50 requests / 5 seconds (= 10/s). We run the
bucket at 8/s with a burst of 8, which keeps any 5-second window at roughly
48 requests — a deliberate safety margin under 50.

iTunes publishes no hard number and throttles aggressively/opaquely, so we
keep a conservative global ceiling whose main job is to stop a thundering
herd of artist threads from all hitting the search endpoint at the same
instant. All four values can be overridden via environment variables for
tuning without a code change.
"""
import os
import threading
import time


class TokenBucket:
    """A classic token-bucket limiter, safe to share across threads."""

    def __init__(self, rate: float, burst: float, name: str = ""):
        self.rate = float(rate)          # tokens added per second
        self.capacity = float(burst)     # max tokens the bucket can hold
        self._tokens = float(burst)      # start full so the first calls are instant
        self._last = time.monotonic()
        self._lock = threading.Lock()
        self.name = name

    def acquire(self, tokens: float = 1.0) -> None:
        """Block until ``tokens`` are available, then consume them.

        Sleeping happens outside the lock so waiting threads never block the
        refill bookkeeping for everyone else.
        """
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                # Refill proportional to elapsed time, capped at capacity.
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                # Not enough yet — work out how long until the deficit accrues.
                deficit = tokens - self._tokens
                wait = deficit / self.rate if self.rate > 0 else 0.25
            # Re-check at least every 250ms to stay responsive and fair.
            time.sleep(min(wait, 0.25))


def _envfloat(name: str, default: float) -> float:
    try:
        v = os.getenv(name)
        return float(v) if v else default
    except (TypeError, ValueError):
        return default


# Deezer: documented 50 req / 5 s. 8/s sustained + burst 8 → ~48 per 5s window.
deezer_limiter = TokenBucket(
    rate=_envfloat("DEEZER_RATE", 8.0),
    burst=_envfloat("DEEZER_BURST", 8.0),
    name="deezer",
)

# iTunes: undocumented per-IP throttle. Conservative global ceiling that
# mainly smooths start-up bursts; lower it via ITUNES_RATE if you see 403s.
itunes_limiter = TokenBucket(
    rate=_envfloat("ITUNES_RATE", 10.0),
    burst=_envfloat("ITUNES_BURST", 10.0),
    name="itunes",
)
