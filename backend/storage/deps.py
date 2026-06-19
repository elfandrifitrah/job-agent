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
    """Yield a StorageBackend — PostgreSQL if available, JSON fallback otherwise.

    Only catches errors during the initial connection test. Errors during
    endpoint operations (e.g. constraint violations) propagate normally.
    """
    session: AsyncSession | None = None
    try:
        session = AsyncSessionLocal()
        await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning("PostgreSQL unavailable (%s), falling back to JSON storage", e)
        if session is not None:
            await session.close()
        global _fallback_backend
        if _fallback_backend is None:
            _fallback_backend = JsonBackend()
        yield _fallback_backend
        return

    backend = PostgresBackend(session)
    try:
        yield backend
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
