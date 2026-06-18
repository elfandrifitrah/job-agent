"""
Tests for the database ORM models and conversion helpers.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.models.db_models import (
    ApplicationModel,
    JobModel,
    ProfileModel,
    SessionModel,
    job_to_orm,
    profile_to_orm,
    _uuid,
)
from backend.models.profile import (
    ApplicationStatus,
    CandidateProfile,
    Education,
    Experience,
    JobPosting,
    SeniorityLevel,
    Skill,
)


class TestProfileModel:
    def test_create_profile_model(self):
        p = ProfileModel(
            id=_uuid(),
            full_name="Alex Chen",
            email="alex@example.com",
            years_of_experience=6.0,
            seniority="senior",
        )
        assert p.id is not None
        assert p.full_name == "Alex Chen"
        assert p.seniority == "senior"

    def test_profile_defaults(self):
        p = ProfileModel(id=_uuid())
        assert p.id is not None
        assert p.remote_preferred is False or p.remote_preferred is None


class TestJobModel:
    def test_create_job_model(self):
        j = JobModel(
            id=_uuid(),
            title="Senior Engineer",
            company="TechCorp",
            source="linkedin",
            seniority="senior",
        )
        assert j.id is not None
        assert j.title == "Senior Engineer"
        assert j.remote is False or j.remote is None


class TestApplicationModel:
    def test_create_application_model(self):
        app = ApplicationModel(
            id=_uuid(),
            profile_id="p1",
            job_id="j1",
            match_score=0.85,
            status=ApplicationStatus.MATCHED.value,
        )
        assert app.id is not None
        assert app.status == "matched"
        assert app.fields_filled == 0 or app.fields_filled is None


class TestSessionModel:
    def test_create_session_model(self):
        s = SessionModel(id=_uuid(), profile_id="p1", total_jobs=5, status="running")
        assert s.id is not None
        assert s.status == "running"
        assert s.total_jobs == 5


class TestConversionHelpers:
    def test_profile_to_orm(self):
        profile = CandidateProfile(
            full_name="Test User",
            email="test@example.com",
            skills=[Skill(name="Python", category="language")],
            experiences=[Experience(company="Acme", title="Engineer")],
            education=[Education(institution="MIT")],
            years_of_experience=5.0,
            seniority=SeniorityLevel.SENIOR,
        )
        orm = profile_to_orm(profile)
        assert orm.full_name == "Test User"
        assert orm.email == "test@example.com"
        assert len(orm.skills) == 1
        assert orm.skills[0]["name"] == "Python"

    def test_job_to_orm(self):
        job = JobPosting(
            id="ext-123",
            title="Senior Engineer",
            company="TechCorp",
            description="Build things with Python",
            remote=True,
            source="linkedin",
            skills_required=["Python", "React"],
        )
        orm = job_to_orm(job)
        assert orm.external_id == "ext-123"
        assert orm.title == "Senior Engineer"
        assert orm.remote is True
        assert len(orm.skills_required) == 2
