"""
Tests for the /api/cover-letter/generate endpoint.

Uses the in-memory SQLite test database via conftest fixtures.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from backend.models.db_models import ProfileModel, JobModel


async def _seed_profile(session, **overrides):
    """Insert a test profile and return its ID."""
    data = {
        "full_name": "Alex Chen",
        "email": "alex@example.com",
        "phone": "",
        "location": "Remote",
        "linkedin_url": "",
        "github_url": "",
        "years_of_experience": 5.0,
        "seniority": "senior",
        "remote_preferred": True,
        "target_roles": ["Software Engineer"],
        "preferred_locations": ["Remote"],
        "raw_text": "Experienced Python developer with React skills.",
        "skills": [
            {"name": "Python", "category": "language", "confidence": 0.9, "mentions": 5},
            {"name": "React", "category": "framework", "confidence": 0.8, "mentions": 3},
        ],
        "experiences": [{
            "company": "TechCorp",
            "title": "Senior Engineer",
            "description": "Built APIs",
            "start_date": "2021",
            "end_date": "Present",
        }],
        "education": [],
        "source_file": "test.pdf",
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
        "title": "Senior Backend Engineer",
        "company": "Stripe",
        "location": "San Francisco, CA",
        "description": "Build payment infrastructure APIs with Python and PostgreSQL.",
        "url": "https://stripe.com/jobs",
        "source": "linkedin",
        "remote": True,
        "seniority": "senior",
        "skills_required": ["Python", "PostgreSQL", "API Design"],
    }
    data.update(overrides)
    job = JobModel(**data)
    session.add(job)
    await session.flush()
    return job.id


class TestCoverLetterAPI:
    @pytest.mark.asyncio
    async def test_generate_with_valid_profile_and_job(self, client: AsyncClient, db_engine):
        """Generate a cover letter for a valid profile+job pair."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            pid = await _seed_profile(session)
            jid = await _seed_job(session)
            await session.commit()

        resp = await client.post(
            "/api/cover-letter/generate",
            json={"profile_id": pid, "job_id": jid, "tone": "professional"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "letter_text" in data
        assert len(data["letter_text"]) > 100
        assert data["word_count"] > 0
        assert data["character_count"] > 0
        assert "letter_path" in data
        assert "Stripe" in data["letter_text"]
        assert "Senior Backend Engineer" in data["letter_text"]
        assert "Alex Chen" in data["letter_text"]

    @pytest.mark.asyncio
    async def test_generate_no_tone_defaults_to_professional(self, client: AsyncClient, db_engine):
        """Tone should default to 'professional' when not provided."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            pid = await _seed_profile(session)
            jid = await _seed_job(session)
            await session.commit()

        resp = await client.post(
            "/api/cover-letter/generate",
            json={"profile_id": pid, "job_id": jid},
        )
        assert resp.status_code == 200
        assert "letter_text" in resp.json()

    @pytest.mark.asyncio
    async def test_generate_profile_not_found(self, client: AsyncClient):
        """Should return 404 when profile doesn't exist."""
        resp = await client.post(
            "/api/cover-letter/generate",
            json={"profile_id": "nonexistent", "job_id": "nonexistent"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_job_not_found(self, client: AsyncClient, db_engine):
        """Should return 404 when job doesn't exist."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        async with async_sessionmaker(db_engine, class_=AsyncSession)() as session:
            pid = await _seed_profile(session)
            await session.commit()

        resp = await client.post(
            "/api/cover-letter/generate",
            json={"profile_id": pid, "job_id": "nonexistent"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_missing_params(self, client: AsyncClient):
        """Should return 422 for missing required fields."""
        resp = await client.post(
            "/api/cover-letter/generate",
            json={},
        )
        assert resp.status_code == 422
