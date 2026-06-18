"""
FastAPI dependency — provides an auto-detecting storage backend.

Tries PostgreSQL first; if unavailable, falls back to JSON file storage
so the dashboard API remains functional without a database.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.storage.backend import StorageBackend
from backend.storage.json_backend import JsonBackend
from backend.storage.postgres_backend import PostgresBackend

logger = logging.getLogger(__name__)

_fallback_backend: JsonBackend | None = None


async def get_backend() -> AsyncGenerator[StorageBackend, None]:
    """Yield a StorageBackend — PostgreSQL if available, JSON fallback otherwise."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            backend = PostgresBackend(session)
            logger.debug("Using PostgreSQL storage backend")
            yield backend
            await session.commit()
    except Exception as e:
        logger.warning("PostgreSQL unavailable (%s), falling back to JSON storage", e)
        global _fallback_backend
        if _fallback_backend is None:
            _fallback_backend = JsonBackend()
        yield _fallback_backend
