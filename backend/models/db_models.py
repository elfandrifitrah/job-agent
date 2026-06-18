"""
SQLAlchemy ORM models — replaces JSONStorage with proper PostgreSQL tables.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

from backend.models.profile import ApplicationStatus, SeniorityLevel

Base = declarative_base()


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    """Return naive UTC datetime (asyncpg requires naive for TIMESTAMP WITHOUT TIME ZONE)."""
    return datetime.now(UTC).replace(tzinfo=None)


# ─── Candidate Profile ──────────────────────────────────────────────────────

class ProfileModel(Base):
    """Stores parsed candidate profiles."""
    __tablename__ = "profiles"

    id = Column(String(36), primary_key=True, default=_uuid)
    full_name = Column(String(255), default="")
    email = Column(String(255), default="")
    phone = Column(String(50), default="")
    location = Column(String(255), default="")
    linkedin_url = Column(String(500), default="")
    github_url = Column(String(500), default="")
    portfolio_url = Column(String(500), default="")

    years_of_experience = Column(Float, default=0.0)
    seniority = Column(String(20), default=SeniorityLevel.UNKNOWN.value)
    remote_preferred = Column(Boolean, default=False)
    target_roles = Column(JSON, default=list)
    preferred_locations = Column(JSON, default=list)

    raw_text = Column(Text, default="")
    skills = Column(JSON, default=list)        # list of Skill dicts
    experiences = Column(JSON, default=list)    # list of Experience dicts
    education = Column(JSON, default=list)      # list of Education dicts

    source_file = Column(String(500), default="")
    parsed_at = Column(DateTime, default=_utcnow)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    applications = relationship("ApplicationModel", back_populates="profile", cascade="all, delete-orphan")


# ─── Job Posting ────────────────────────────────────────────────────────────

class JobModel(Base):
    """Stores discovered job postings."""
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=_uuid)
    external_id = Column(String(50), default="", index=True)  # Source-side ID
    title = Column(String(255), default="")
    company = Column(String(255), default="")
    location = Column(String(255), default="")
    description = Column(Text, default="")
    url = Column(String(1000), default="")
    source = Column(String(50), default="")        # linkedin, indeed, adzuna
    salary_range = Column(String(100), nullable=True)
    remote = Column(Boolean, default=False)
    posted_date = Column(String(50), nullable=True)
    skills_required = Column(JSON, default=list)
    seniority = Column(String(20), default=SeniorityLevel.UNKNOWN.value)

    created_at = Column(DateTime, default=_utcnow)

    # Relationships
    applications = relationship("ApplicationModel", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("external_id", "source", name="uq_job_source"),
    )


# ─── Application Record ─────────────────────────────────────────────────────

class ApplicationModel(Base):
    """Tracks the lifecycle of one job application."""
    __tablename__ = "applications"

    id = Column(String(36), primary_key=True, default=_uuid)
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False, index=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False, index=True)

    match_score = Column(Float, default=0.0)
    status = Column(String(20), default=ApplicationStatus.PENDING.value, index=True)

    skill_overlap = Column(JSON, default=list)
    skill_gaps = Column(JSON, default=list)

    cover_letter_path = Column(String(500), nullable=True)
    screenshot_path = Column(String(500), nullable=True)
    ats_name = Column(String(50), default="")
    fields_filled = Column(Integer, default=0)
    total_fields = Column(Integer, default=0)

    submitted_at = Column(DateTime, nullable=True)
    response_received_at = Column(DateTime, nullable=True)
    notes = Column(Text, default="")
    error_log = Column(Text, default="")

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    profile = relationship("ProfileModel", back_populates="applications")
    job = relationship("JobModel", back_populates="applications")


# ─── Automation Session ─────────────────────────────────────────────────────

class SessionModel(Base):
    """Logs an automation session (batch of applications)."""
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=True, index=True)

    status = Column(String(20), default="running")  # running, completed, failed, aborted
    total_jobs = Column(Integer, default=0)
    submitted = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    blocked = Column(Integer, default=0)
    skipped = Column(Integer, default=0)

    started_at = Column(DateTime, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_log = Column(Text, default="")


# ─── Pydantic → SQLAlchemy helpers ──────────────────────────────────────────

def profile_to_orm(profile) -> ProfileModel:
    """Convert a Pydantic CandidateProfile to a SQLAlchemy ProfileModel."""
    return ProfileModel(
        full_name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        location=profile.location,
        linkedin_url=profile.linkedin_url,
        github_url=profile.github_url,
        portfolio_url=profile.portfolio_url,
        years_of_experience=profile.years_of_experience,
        seniority=profile.seniority.value,
        remote_preferred=profile.remote_preferred,
        target_roles=profile.target_roles,
        preferred_locations=profile.preferred_locations,
        raw_text=profile.raw_text[:100_000] if profile.raw_text else "",
        skills=[s.model_dump() for s in profile.skills],
        experiences=[e.model_dump() for e in profile.experiences],
        education=[e.model_dump() for e in profile.education],
        source_file=profile.source_file,
    )


def job_to_orm(job) -> JobModel:
    """Convert a Pydantic JobPosting to a SQLAlchemy JobModel."""
    return JobModel(
        external_id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        description=job.description[:100_000] if job.description else "",
        url=job.url,
        source=job.source,
        salary_range=job.salary_range,
        remote=job.remote,
        posted_date=job.posted_date,
        skills_required=job.skills_required,
        seniority=job.seniority.value,
    )
