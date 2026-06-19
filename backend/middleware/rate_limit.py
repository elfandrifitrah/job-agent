"""
Simple in-memory rate limiter middleware.

Tracks requests per client IP with a sliding window.  Designed for
single-worker deployments (HF Spaces, local dev).  No external
dependencies (Redis etc.) required.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window rate limiter.

    Parameters
    ----------
    max_requests : int
        Maximum requests allowed in the window.
    window_seconds : int
        Sliding window size in seconds.
    paths : list[str] | None
        If given, only apply limiting to paths starting with these prefixes.
        If None, apply to all paths.
    """

    def __init__(
        self,
        app,
        max_requests: int = 60,
        window_seconds: int = 60,
        paths: list[str] | None = None,
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.paths = paths or []
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()

    def _client_ip(self, request: Request) -> str:
        # Only trust X-Forwarded-For if behind a known reverse proxy
        # (e.g., HF Spaces, Cloudflare, nginx). Otherwise use direct client IP.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded and request.headers.get("x-forwarded-host"):
            # Only trust if x-forwarded-host is also present (reverse proxy indicator)
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < self.window_seconds * 2:
            return
        cutoff = now - self.window_seconds
        stale_keys = [k for k, v in self._hits.items() if not v or v[-1] < cutoff]
        for k in stale_keys:
            del self._hits[k]
        self._last_cleanup = now

    async def dispatch(self, request: Request, call_next: Callable):
        if self.paths and not any(request.url.path.startswith(p) for p in self.paths):
            return await call_next(request)

        # Only rate-limit mutation requests (POST, PUT, PATCH, DELETE)
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        self._cleanup()

        ip = self._client_ip(request)
        now = time.monotonic()
        cutoff = now - self.window_seconds

        hits = self._hits[ip]
        # Remove expired entries
        self._hits[ip] = hits = [t for t in hits if t > cutoff]

        if len(hits) >= self.max_requests:
            retry_after = int(hits[0] - cutoff) + 1
            logger.warning("Rate limit exceeded for %s on %s", ip, request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        return await call_next(request)
