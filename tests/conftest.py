"""
Shared pytest fixtures — provides an in-memory SQLite async database
so API tests run without PostgreSQL.

Usage:
    All fixtures are autouse-scoped to function. Just import this conftest
    (via pytest's automatic conftest discovery) and any test in the tests/
    directory gets a fresh SQLite database per test.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

import pytest
import pytest_asyncio


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (ML/API-dependent, not run in quick mode)")
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import override_engine, override_session_local
from backend.models.db_models import Base

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a fresh in-memory SQLite async engine per test function."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def _override_db_deps(db_engine):
    """Automatically override the global DB engine and session factory for every test."""
    session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    override_engine(db_engine)
    override_session_local(session_factory)
    yield
    # Engine is disposed by the db_engine fixture teardown; globals will be
    # re-overridden on the next test anyway.


@pytest_asyncio.fixture(scope="function")
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client wired to the FastAPI app with the SQLite test DB.

    Imports are deferred so the DB overrides take effect before the app
    tries to connect.
    """
    from backend.main import app
    from backend.database import AsyncSessionLocal

    async def _get_db_override():
        async with AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    from backend.database import get_db
    app.dependency_overrides[get_db] = _get_db_override

    # Also override the storage backend dependency so the new storage layer
    # uses the test database session instead of trying real PostgreSQL.
    from backend.storage.backend import StorageBackend
    from backend.storage.postgres_backend import PostgresBackend

    async def _get_backend_override():
        async with AsyncSessionLocal() as session:
            backend = PostgresBackend(session)
            try:
                yield backend
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    from backend.storage.deps import get_backend
    app.dependency_overrides[get_backend] = _get_backend_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()
