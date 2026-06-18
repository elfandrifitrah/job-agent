"""
Database connection and session management.
Phase 4: async SQLAlchemy + PostgreSQL with Alembic migrations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings
from backend.models.db_models import ApplicationModel, Base, JobModel, ProfileModel, SessionModel

logger = logging.getLogger(__name__)

# ─── Async Engine ───────────────────────────────────────────────────────────
# Engine and session factory are module-level but can be overridden for testing
# via override_engine() / override_session_local().

def _create_default_engine():
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

engine = _create_default_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ─── Test helpers — allow tests to swap in an in-memory SQLite engine ────────

def override_engine(new_engine) -> None:
    """Replace the global engine (e.g. with an SQLite test engine)."""
    global engine
    engine = new_engine


def override_session_local(new_session_factory) -> None:
    """Replace the global session factory."""
    global AsyncSessionLocal
    AsyncSessionLocal = new_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async database session.
    Returns 503 if PostgreSQL is unavailable (caller should handle gracefully).
    """
    try:
        async with AsyncSessionLocal() as session:
            try:
                # Test connection
                await session.execute(text("SELECT 1"))
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    except Exception as e:
        from fastapi import HTTPException
        logger.warning("Database unavailable: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable. Start PostgreSQL or use the CLI with JSON storage.") from e


async def init_db() -> None:
    """Create all tables if they don't exist. For production, use Alembic instead."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created / verified")
    except Exception as e:
        logger.warning("Database init failed (may be running without PG): %s", e)


async def check_db() -> bool:
    """Quick health check — returns True if the database is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.debug("Database health check failed: %s", e)
        return False


# ─── Fallback JSON storage (when PostgreSQL is unavailable) ─────────────────


class JSONStorage:
    """Simple JSON-file-based storage for development without PostgreSQL.
    Used as a fallback when the database is not available.
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or settings.data_dir / "store.json"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict:
        if self.db_path.exists():
            try:
                return json.loads(self.db_path.read_text())
            except json.JSONDecodeError:
                logger.warning("Corrupted store.json — reinitialising")
                self.db_path.unlink(missing_ok=True)
        return {"profiles": [], "applications": [], "jobs": []}

    def _save(self) -> None:
        self.db_path.write_text(json.dumps(self._data, indent=2, default=str))

    def save_profile(self, profile: dict) -> None:
        self._data["profiles"].append(profile)
        self._save()

    def get_profiles(self) -> list[dict]:
        return self._data.get("profiles", [])

    def get_latest_profile(self) -> dict | None:
        profiles = self._data.get("profiles", [])
        return profiles[-1] if profiles else None

    def save_application(self, app: dict) -> None:
        self._data["applications"].append(app)
        self._save()

    def get_applications(self) -> list[dict]:
        return self._data.get("applications", [])

    def save_jobs(self, jobs: list[dict]) -> None:
        self._data["jobs"] = jobs
        self._save()

    def get_jobs(self) -> list[dict]:
        return self._data.get("jobs", [])

    def clear(self) -> None:
        self._data = {"profiles": [], "applications": [], "jobs": []}
        self._save()


# Global singleton
storage = JSONStorage()
