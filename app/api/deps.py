from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request, Response, status
from fastapi import HTTPException

from app.config import Settings, get_settings
from app.infra.rate_limit import InMemoryFixedWindowRateLimiter, RateLimitConfig


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def _get_limiter(request: Request) -> InMemoryFixedWindowRateLimiter:
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        limiter = InMemoryFixedWindowRateLimiter()
        request.app.state.rate_limiter = limiter
    return limiter


def rate_limit(route_id: str) -> Callable[[Request, Response, Settings], None]:
    def _dependency(request: Request, response: Response, settings: Settings = Depends(get_settings)) -> None:
        limiter = _get_limiter(request)
        ip = _client_ip(request)
        key = f"{route_id}:{ip}"
        cfg = RateLimitConfig(
            window_seconds=int(settings.rate_limit_window_seconds),
            max_requests=int(settings.rate_limit_max_requests),
        )
        result = limiter.check(key=key, config=cfg)

        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_in_seconds)

        if not result.allowed:
            response.headers["Retry-After"] = str(result.reset_in_seconds)
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited")

    return _dependency
