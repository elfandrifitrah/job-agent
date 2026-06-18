"""
Tests for the API key authentication middleware.

Covers both the "auth disabled" path (default: API_KEY = "") and the
"auth enabled" path (API_KEY set via settings override).

Test methodology:
  - Default tests use the `client` fixture (API_KEY = "")
  - Enforcement tests use `enforcing_client` fixture (API_KEY = "test-key-123")
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture(scope="function")
async def enforcing_client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client with API_KEY auth enforcement enabled."""
    from unittest.mock import patch
    from backend.main import app
    from backend.database import AsyncSessionLocal

    with patch("backend.middleware.auth.settings.api_key", "test-key-123"):
        # Override storage backend dependency
        from backend.storage.postgres_backend import PostgresBackend
        from backend.storage.deps import get_backend

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

        app.dependency_overrides[get_backend] = _get_backend_override

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac

        app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Auth disabled (default: API_KEY = "")
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthDisabled:
    @pytest.mark.asyncio
    async def test_api_access_without_key(self, client: AsyncClient):
        """When API_KEY is empty, API routes should work without a key."""
        resp = await client.get("/api/profiles")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_accessible(self, client: AsyncClient):
        """Health endpoint is always public."""
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_docs_accessible(self, client: AsyncClient):
        """Documentation pages are always public."""
        for path in ["/docs", "/redoc", "/openapi.json"]:
            resp = await client.get(path)
            assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_options_bypasses_auth(self, client: AsyncClient):
        """OPTIONS preflight requests pass through without auth."""
        resp = await client.options("/api/profiles")
        assert resp.status_code != 401


# ═══════════════════════════════════════════════════════════════════════════════
# Auth enabled (API_KEY = "test-key-123")
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthEnabled:
    @pytest.mark.asyncio
    async def test_no_key_returns_401(self, enforcing_client: AsyncClient):
        """Without X-API-Key, /api/* returns 401."""
        resp = await enforcing_client.get("/api/profiles")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_key_returns_401(self, enforcing_client: AsyncClient):
        """Wrong API key returns 401."""
        resp = await enforcing_client.get(
            "/api/profiles",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_correct_key_returns_200(self, enforcing_client: AsyncClient):
        """Correct API key grants access."""
        resp = await enforcing_client.get(
            "/api/profiles",
            headers={"X-API-Key": "test-key-123"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_still_public(self, enforcing_client: AsyncClient):
        """Health endpoint is accessible without a key even when auth is enabled."""
        resp = await enforcing_client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_docs_still_public(self, enforcing_client: AsyncClient):
        """Documentation pages are still accessible without a key."""
        resp = await enforcing_client.get("/docs")
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_options_still_bypasses(self, enforcing_client: AsyncClient):
        """OPTIONS requests bypass auth even when auth is enabled."""
        resp = await enforcing_client.options("/api/profiles")
        assert resp.status_code != 401
