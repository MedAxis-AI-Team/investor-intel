from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, Response, status

from app.config import Settings, get_settings
from app.infra.rate_limit import InMemoryFixedWindowRateLimiter, RateLimitConfig


def get_request_id() -> str:
    return uuid.uuid4().hex


def require_api_key(
    settings: Settings = Depends(get_settings),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


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
        api_key = request.headers.get("x-api-key", "missing")
        ip = _client_ip(request)
        key = f"{route_id}:{ip}:{api_key}"
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
