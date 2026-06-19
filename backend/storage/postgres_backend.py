"""
PostgreSQL-backed storage implementation using async SQLAlchemy.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.models.db_models import ApplicationModel, JobModel, ProfileModel
from backend.storage.backend import AppStats, SourceBreakdown, StorageBackend

logger = logging.getLogger(__name__)


class PostgresBackend(StorageBackend):
    """Storage backend backed by PostgreSQL via async SQLAlchemy."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def is_available(self) -> bool:
        try:
            await self.db.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    # ─── Profiles ───────────────────────────────────────────────────────────

    async def list_profiles(self) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(ProfileModel).order_by(ProfileModel.parsed_at.desc())
        )
        return [_profile_to_dict(p) for p in result.scalars().all()]

    async def get_profile(self, profile_id: str) -> Optional[dict[str, Any]]:
        result = await self.db.execute(
            select(ProfileModel).where(ProfileModel.id == profile_id)
        )
        p = result.scalar_one_or_none()
        return _profile_to_dict(p, detailed=True) if p else None

    async def create_profile(self, data: dict[str, Any]) -> str:
        from backend.models.db_models import profile_to_orm, ProfileModel
        from backend.models.profile import CandidateProfile

        # Allow callers to specify a fixed id (e.g. 'local')
        fixed_id = data.pop("id", None)

        profile = CandidateProfile(**data)
        orm = profile_to_orm(profile)

        if fixed_id:
            orm.id = fixed_id

        self.db.add(orm)
        await self.db.flush()
        return str(orm.id)

    async def delete_profile(self, profile_id: str) -> bool:
        result = await self.db.execute(
            select(ProfileModel).where(ProfileModel.id == profile_id)
        )
        p = result.scalar_one_or_none()
        if not p:
            return False
        await self.db.delete(p)
        return True

    # ─── Jobs ───────────────────────────────────────────────────────────────

    async def list_jobs(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(JobModel).order_by(JobModel.created_at.desc()).limit(limit).offset(offset)
        )
        return [_job_to_dict(j) for j in result.scalars().all()]

    async def store_jobs(self, jobs: list[dict[str, Any]]) -> int:
        from sqlalchemy import select
        from backend.models.db_models import job_to_orm, JobModel
        from backend.models.profile import JobPosting

        existing_result = await self.db.execute(select(JobModel.external_id))
        existing_ids = {row[0] for row in existing_result.all()}

        count = 0
        for job_data in jobs:
            job = JobPosting(**job_data)
            if job.id in existing_ids:
                continue
            orm = job_to_orm(job)
            self.db.add(orm)
            existing_ids.add(job.id)
            count += 1
        if count:
            await self.db.flush()
        return count

    async def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        result = await self.db.execute(
            select(JobModel).where(JobModel.id == job_id)
        )
        j = result.scalar_one_or_none()
        return _job_to_dict(j) if j else None

    async def delete_job(self, job_id: str) -> bool:
        result = await self.db.execute(
            select(JobModel).where(JobModel.id == job_id)
        )
        j = result.scalar_one_or_none()
        if not j:
            return False
        await self.db.delete(j)
        return True

    async def count_jobs_by_source(self) -> list[SourceBreakdown]:
        result = await self.db.execute(
            select(JobModel.source, func.count(JobModel.id).label("count"))
            .group_by(JobModel.source)
            .order_by(func.count(JobModel.id).desc())
        )
        return [SourceBreakdown(source=row.source, count=row.count) for row in result]

    # ─── Applications ───────────────────────────────────────────────────────

    async def list_applications(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        # Use eager loading to avoid N+1 queries
        query = (
            select(ApplicationModel)
            .options(joinedload(ApplicationModel.job))
            .order_by(ApplicationModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            query = query.where(ApplicationModel.status == status)
        if profile_id:
            query = query.where(ApplicationModel.profile_id == profile_id)

        result = await self.db.execute(query)
        # Use unique() because joinedload can produce duplicate rows
        apps = result.unique().scalars().all()

        return [
            _app_with_job_dict(a)
            for a in apps
        ]

    async def get_application(self, app_id: str) -> Optional[dict[str, Any]]:
        result = await self.db.execute(
            select(ApplicationModel)
            .options(joinedload(ApplicationModel.job))
            .where(ApplicationModel.id == app_id)
        )
        a = result.unique().scalar_one_or_none()
        return _app_with_job_dict(a) if a else None

    async def create_application(self, data: dict[str, Any]) -> str:
        # Only pass fields that ApplicationModel actually has
        valid_keys = {c.name for c in ApplicationModel.__table__.columns}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        orm = ApplicationModel(**filtered)
        self.db.add(orm)
        await self.db.flush()
        return str(orm.id)

    async def update_application_status(self, app_id: str, status: str) -> bool:
        result = await self.db.execute(
            select(ApplicationModel).where(ApplicationModel.id == app_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            return False
        app.status = status
        if status == "submitted" and not app.submitted_at:
            app.submitted_at = datetime.now(UTC).replace(tzinfo=None)
        return True

    async def delete_application(self, app_id: str) -> bool:
        result = await self.db.execute(
            select(ApplicationModel).where(ApplicationModel.id == app_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            return False
        await self.db.delete(app)
        return True

    async def count_applications_by_status(self) -> dict[str, int]:
        result = await self.db.execute(
            select(ApplicationModel.status, func.count(ApplicationModel.id).label("count"))
            .group_by(ApplicationModel.status)
        )
        return {row.status: row.count for row in result}

    # ─── Dashboard Aggregates ───────────────────────────────────────────────

    async def get_stats(self) -> AppStats:
        profile_count = (
            await self.db.execute(select(func.count(ProfileModel.id)))
        ).scalar() or 0

        job_count = (
            await self.db.execute(select(func.count(JobModel.id)))
        ).scalar() or 0

        app_count = (
            await self.db.execute(select(func.count(ApplicationModel.id)))
        ).scalar() or 0

        submitted_count = (
            await self.db.execute(
                select(func.count(ApplicationModel.id))
                .where(ApplicationModel.status == "submitted")
            )
        ).scalar() or 0

        avg_score = (
            await self.db.execute(
                select(func.avg(ApplicationModel.match_score))
                .where(ApplicationModel.match_score > 0)
            )
        ).scalar() or 0.0

        today_start = datetime.now(UTC).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
        today_count = (
            await self.db.execute(
                select(func.count(ApplicationModel.id))
                .where(ApplicationModel.created_at >= today_start)
            )
        ).scalar() or 0

        return AppStats(
            total_profiles=profile_count,
            total_jobs=job_count,
            total_applications=app_count,
            submitted_applications=submitted_count,
            avg_match_score=float(avg_score),
            applications_today=today_count,
            database_connected=True,
        )


# ─── Serialisation helpers ──────────────────────────────────────────────────


def _profile_to_dict(p: ProfileModel, detailed: bool = False) -> dict[str, Any]:
    base = {
        "id": p.id,
        "full_name": p.full_name,
        "email": p.email,
        "phone": p.phone,
        "location": p.location,
        "linkedin_url": p.linkedin_url,
        "github_url": p.github_url,
        "years_of_experience": p.years_of_experience,
        "seniority": p.seniority,
        "remote_preferred": p.remote_preferred,
        "skills_count": len(p.skills or []),
        "experiences_count": len(p.experiences or []),
        "parsed_at": p.parsed_at.isoformat() if p.parsed_at else None,
        "source_file": p.source_file,
    }
    if detailed:
        base.update({
            "raw_text": p.raw_text or "",
            "skills": p.skills or [],
            "experiences": p.experiences or [],
            "education": p.education or [],
            "target_roles": p.target_roles or [],
            "preferred_locations": p.preferred_locations or [],
            "portfolio_url": p.portfolio_url or "",
        })
    return base


def _job_to_dict(j: JobModel) -> dict[str, Any]:
    return {
        "id": j.id,
        "external_id": j.external_id,
        "title": j.title,
        "company": j.company,
        "location": j.location,
        "description": j.description,
        "url": j.url,
        "source": j.source,
        "salary_range": j.salary_range,
        "remote": j.remote,
        "posted_date": j.posted_date,
        "skills_required": j.skills_required or [],
        "seniority": j.seniority,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }


def _app_with_job_dict(a: ApplicationModel) -> dict[str, Any]:
    """Convert an ApplicationModel (with joined JobModel) to a dict."""
    job = a.job  # Loaded via joinedload
    return {
        "id": a.id,
        "profile_id": a.profile_id,
        "job_id": a.job_id,
        "job_title": job.title if job else "",
        "company": job.company if job else "",
        "match_score": a.match_score,
        "status": a.status,
        "skill_overlap": a.skill_overlap or [],
        "skill_gaps": a.skill_gaps or [],
        "cover_letter_path": a.cover_letter_path,
        "screenshot_path": a.screenshot_path,
        "ats_name": a.ats_name,
        "fields_filled": a.fields_filled,
        "total_fields": a.total_fields,
        "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
