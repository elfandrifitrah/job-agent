"""
Lightweight request timing middleware.

Logs request duration and flags slow requests (> 2s).  No external
dependencies required — uses stdlib `time.monotonic` and stdlib `logging`.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("backend.middleware.timing")

# Requests slower than this (seconds) get a warning log
SLOW_THRESHOLD = 2.0


class TimingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, and duration."""

    async def dispatch(self, request: Request, call_next: Callable):
        start = time.monotonic()
        response = await call_next(request)
        elapsed = time.monotonic() - start

        status = response.status_code
        method = request.method
        path = request.url.path
        client = request.client.host if request.client else "-"

        if elapsed >= SLOW_THRESHOLD:
            logger.warning(
                "SLOW %s %s %d %.3fs client=%s",
                method, path, status, elapsed, client,
            )
        else:
            logger.info(
                "%s %s %d %.3fs client=%s",
                method, path, status, elapsed, client,
            )

        response.headers["X-Process-Time"] = f"{elapsed:.3f}"
        return response
