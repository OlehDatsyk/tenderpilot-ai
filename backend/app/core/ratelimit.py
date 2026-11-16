"""Small in-memory sliding-window rate limiter.

Limits are per process. For multi-instance deployments put a shared limiter (e.g. Redis) or the
platform's edge rate limiting in front of the API - see SECURITY.md.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float = 60.0) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = int(window_seconds - (now - bucket[0])) + 1
                return False, retry_after
            bucket.append(now)
            if len(self._hits) > 50_000:  # crude memory bound
                for k in list(self._hits)[:10_000]:
                    if not self._hits[k]:
                        del self._hits[k]
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    if get_settings().trusted_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Use the right-most entry: it is appended by the trusted platform proxy. Left-most entries are
            # client-controlled and would let an attacker rotate fake IPs to bypass rate limits.
            return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _enforce(request: Request, scope: str, limit: int) -> None:
    allowed, retry_after = limiter.hit(f"{scope}:{client_ip(request)}", limit)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait and try again.",
            headers={"Retry-After": str(retry_after)},
        )


def auth_rate_limit(request: Request) -> None:
    _enforce(request, f"auth:{request.url.path}", get_settings().rate_limit_auth_per_minute)


def ai_rate_limit(request: Request) -> None:
    _enforce(request, "ai", get_settings().rate_limit_ai_per_minute)
