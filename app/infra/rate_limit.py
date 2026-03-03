from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitConfig:
    window_seconds: int
    max_requests: int


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_in_seconds: int


class InMemoryFixedWindowRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, int]] = {}

    def check(self, *, key: str, config: RateLimitConfig, now: float | None = None) -> RateLimitResult:
        current = time.monotonic() if now is None else now

        bucket = self._buckets.get(key)
        if bucket is None:
            window_start = current
            count = 0
        else:
            window_start, count = bucket

        elapsed = current - window_start
        if elapsed >= config.window_seconds:
            window_start = current
            count = 0

        next_count = count + 1
        allowed = next_count <= config.max_requests
        stored_count = next_count if allowed else count

        self._buckets[key] = (window_start, stored_count)

        reset_in = max(0, int(config.window_seconds - (current - window_start)))
        remaining = max(0, config.max_requests - stored_count)

        return RateLimitResult(allowed=allowed, remaining=remaining, reset_in_seconds=reset_in)
