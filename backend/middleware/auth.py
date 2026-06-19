"""
API key authentication middleware.

Protects all /api/* routes by requiring a valid API key in the X-API-Key header.
The key is configured via the `API_KEY` environment variable (see backend.config.settings).
Routes that should be public (health, docs, static dashboard) are excluded.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import settings

logger = logging.getLogger(__name__)

# Path prefixes that do not require authentication
PUBLIC_PATHS = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/dashboard",
}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware that validates the X-API-Key header on all /api/* routes.

    In production mode (ENVIRONMENT=production), API_KEY MUST be set.
    In development mode, auth is skipped when API_KEY is empty.
    """

    async def dispatch(self, request: Request, call_next):
        # Allow CORS preflight through (browsers don't send custom headers on OPTIONS)
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        # Allow public paths through
        if any(path.startswith(prefix) for prefix in PUBLIC_PATHS):
            return await call_next(request)

        # Only protect /api/* routes
        if not path.startswith("/api/"):
            return await call_next(request)

        # Skip auth when no key is configured (dev mode only)
        if not settings.api_key:
            if settings.environment == "production":
                logger.error("CRITICAL: API_KEY not set in production mode!")
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"detail": "Server misconfigured: API_KEY required in production."},
                )
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if not api_key or not hmac.compare_digest(api_key, settings.api_key):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing or invalid API key. Provide it via the X-API-Key header."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)


def setup_auth_middleware(app: FastAPI) -> None:
    """Register the API key middleware on the FastAPI app."""
    app.add_middleware(APIKeyMiddleware)
    if settings.api_key:
        logger.info("API key authentication is ENABLED")
    elif settings.environment == "production":
        logger.warning("API key authentication is DISABLED — SECURITY RISK in production!")
    else:
        logger.info("API key authentication is DISABLED (development mode)")
