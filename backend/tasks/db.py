"""
Shared synchronous database engine for Celery background tasks.
Celery workers should use synchronous SQLAlchemy (not async) to avoid
issues with asyncio.run() in forked worker processes.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession

from backend.config import settings

_sync_engine = None


def get_sync_engine():
    """Get or create a shared synchronous SQLAlchemy engine for Celery tasks."""
    global _sync_engine
    if _sync_engine is None:
        # Convert async PG URL to sync URL
        sync_url = settings.database_url
        sync_url = sync_url.replace("+asyncpg", "+psycopg2")
        sync_url = sync_url.replace("postgresql+psycopg2", "postgresql")
        _sync_engine = create_engine(sync_url, pool_pre_ping=True, pool_size=2, max_overflow=4)
    return _sync_engine
