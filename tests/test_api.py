"""
Tests for FastAPI API endpoints.

Uses an in-memory SQLite async database via the conftest.py fixtures.
No PostgreSQL required — all tests run in isolation.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from backend.models.db_models import ApplicationModel, JobModel, ProfileModel


# ─── Helper: seed a profile + job into the test DB ──────────────────────────


async def _seed_profile(session, **overrides):
    """Insert a test profile and return its ID."""
    data = {
        "full_name": "Test User",
        "email": "test@example.com",
        "phone": "+1-555-0000",
        "location": "Remote",
        "linkedin_url": "",
        "github_url": "",
        "years_of_experience": 5.0,
        "seniority": "senior",
        "remote_preferred": True,
        "target_roles": ["Software Engineer"],
        "preferred_locations": ["Remote"],
        "raw_text": "Test CV text",
        "skills": [{"name": "Python", "category": "language", "confidence": 0.9, "mentions": 5}],
        "experiences": [],
        "education": [],
        "source_file": "test.txt",
    }
    data.update(overrides)
    profile = ProfileModel(**data)
    session.add(profile)
    await session.flush()
    return profile.id


async def _seed_job(session, **overrides):
    """Insert a test job and return its ID."""
    data = {
        "external_id": "ext_001",
        "title": "Software Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "description": "Build cool stuff",
        "url": "https://example.com/apply",
        "source": "linkedin",
        "salary_range": "$100K–$150K",
        "remote": True,
        "seniority": "senior",
        "skills_required": ["Python", "React"],
    }
    data.update(overrides)
    job = JobModel(**data)
    session.add(job)
    await session.flush()
    return job.id


# ═══════════════════════════════════════════════════════════════════════════════
# Health & Root
# ═══════════════════════════════════════════════════════════════════════════════


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "version" in data

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "docs" in data

    @pytest.mark.asyncio
    async def test_openapi_docs(self, client: AsyncClient):
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "paths" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Profiles API
# ═══════════════════════════════════════════════════════════════════════════════


class TestProfilesAPI:
    @pytest.mark.asyncio
    async def test_list_profiles_empty(self, client: AsyncClient):
        resp = await client.get("/api/profiles")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_profiles_with_data(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            await _seed_profile(session)
            await session.commit()

        resp = await client.get("/api/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["full_name"] == "Test User"
        assert data[0]["skills_count"] == 1

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, client: AsyncClient):
        resp = await client.get("/api/profiles/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_profile_by_id(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            pid = await _seed_profile(session)
            await session.commit()

        resp = await client.get(f"/api/profiles/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["full_name"] == "Test User"
        assert data["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_delete_profile(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            pid = await _seed_profile(session)
            await session.commit()

        resp = await client.delete(f"/api/profiles/{pid}")
        assert resp.status_code == 204

        # Confirm gone
        resp = await client.get(f"/api/profiles/{pid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_profile_manual(self, client: AsyncClient):
        payload = {
            "full_name": "Manual User",
            "email": "manual@example.com",
            "phone": "",
            "location": "",
            "linkedin_url": "",
            "github_url": "",
            "portfolio_url": "",
            "years_of_experience": 3.0,
            "seniority": "mid",
            "remote_preferred": False,
            "target_roles": [],
            "preferred_locations": [],
            "raw_text": "",
            "skills": [],
            "experiences": [],
            "education": [],
            "source_file": "",
        }
        resp = await client.post("/api/profiles", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["message"] == "Profile created"


# ═══════════════════════════════════════════════════════════════════════════════
# Jobs API
# ═══════════════════════════════════════════════════════════════════════════════


class TestJobsAPI:
    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, client: AsyncClient):
        resp = await client.get("/api/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_jobs_with_data(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            await _seed_job(session)
            await session.commit()

        resp = await client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Software Engineer"
        assert data[0]["company"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, client: AsyncClient):
        resp = await client.get("/api/jobs/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_by_id(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            jid = await _seed_job(session)
            await session.commit()

        resp = await client.get(f"/api/jobs/{jid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Software Engineer"
        assert "description" in data

    @pytest.mark.asyncio
    async def test_delete_job(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            jid = await _seed_job(session)
            await session.commit()

        resp = await client.delete(f"/api/jobs/{jid}")
        assert resp.status_code == 204

        resp = await client.get(f"/api/jobs/{jid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_source(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            await _seed_job(session, source="linkedin", external_id="ext_a")
            await _seed_job(session, source="indeed", external_id="ext_b")
            await session.commit()

        resp = await client.get("/api/jobs?source=linkedin")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["source"] == "linkedin"


# ═══════════════════════════════════════════════════════════════════════════════
# Applications API
# ═══════════════════════════════════════════════════════════════════════════════


class TestApplicationsAPI:
    @pytest.mark.asyncio
    async def test_list_applications_empty(self, client: AsyncClient):
        resp = await client.get("/api/applications")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_applications_with_data(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            pid = await _seed_profile(session)
            jid = await _seed_job(session)
            app = ApplicationModel(
                profile_id=pid,
                job_id=jid,
                match_score=0.85,
                status="submitted",
                skill_overlap=["Python"],
                skill_gaps=[],
            )
            session.add(app)
            await session.commit()

        resp = await client.get("/api/applications")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "submitted"
        assert data[0]["match_score"] == 0.85
        assert data[0]["job_title"] == "Software Engineer"

    @pytest.mark.asyncio
    async def test_application_stats(self, client: AsyncClient):
        resp = await client.get("/api/applications/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "by_status" in data
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_get_application_not_found(self, client: AsyncClient):
        resp = await client.get("/api/applications/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_application_status(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            pid = await _seed_profile(session)
            jid = await _seed_job(session)
            app = ApplicationModel(
                profile_id=pid,
                job_id=jid,
                match_score=0.7,
                status="matched",
            )
            session.add(app)
            await session.flush()
            app_id = app.id
            await session.commit()

        resp = await client.patch(
            f"/api/applications/{app_id}/status",
            json={"status": "applied"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"

    @pytest.mark.asyncio
    async def test_update_application_invalid_status(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            pid = await _seed_profile(session)
            jid = await _seed_job(session)
            app = ApplicationModel(profile_id=pid, job_id=jid, status="matched")
            session.add(app)
            await session.flush()
            app_id = app.id
            await session.commit()

        resp = await client.patch(
            f"/api/applications/{app_id}/status",
            json={"status": "invalid_status"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_application(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            pid = await _seed_profile(session)
            jid = await _seed_job(session)
            app = ApplicationModel(profile_id=pid, job_id=jid, status="pending")
            session.add(app)
            await session.flush()
            app_id = app.id
            await session.commit()

        resp = await client.delete(f"/api/applications/{app_id}")
        assert resp.status_code == 204

        resp = await client.get(f"/api/applications/{app_id}")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard API
# ═══════════════════════════════════════════════════════════════════════════════


class TestDashboardAPI:
    @pytest.mark.asyncio
    async def test_dashboard_health(self, client: AsyncClient):
        resp = await client.get("/api/dashboard/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    @pytest.mark.asyncio
    async def test_dashboard_stats(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            pid = await _seed_profile(session)
            jid = await _seed_job(session)
            for i in range(3):
                session.add(ApplicationModel(
                    profile_id=pid, job_id=jid, match_score=0.8, status="submitted"
                ))
            await session.commit()

        resp = await client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_profiles"] == 1
        assert data["total_jobs"] == 1
        assert data["total_applications"] == 3
        assert data["submitted_applications"] == 3

    @pytest.mark.asyncio
    async def test_dashboard_sources(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            await _seed_job(session, source="linkedin", external_id="ext_x")
            await _seed_job(session, source="indeed", external_id="ext_y")
            await session.commit()

        resp = await client.get("/api/dashboard/sources")
        assert resp.status_code == 200
        data = resp.json()
        sources = {item["source"]: item["count"] for item in data}
        assert sources.get("linkedin") == 1
        assert sources.get("indeed") == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Automation API
# ═══════════════════════════════════════════════════════════════════════════════


class TestAutomationAPI:
    @pytest.mark.asyncio
    async def test_match_no_profile(self, client: AsyncClient):
        resp = await client.post(
            "/api/automation/match",
            json={"profile_id": "nonexistent", "top_k": 5},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_match_no_jobs(self, client: AsyncClient, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            pid = await _seed_profile(session)
            await session.commit()

        resp = await client.post(
            "/api/automation/match",
            json={"profile_id": pid, "top_k": 5},
        )
        assert resp.status_code == 404  # No jobs to match against
