"""
Celery task — background semantic matching of profile against jobs.
Uses synchronous SQLAlchemy to avoid asyncio.run() issues in Celery workers.
"""

from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.orm import Session as SASession

from backend.celery_app import celery_app
from backend.models.db_models import ApplicationModel, JobModel, ProfileModel
from backend.models.profile import ApplicationStatus, CandidateProfile, Education, Experience, JobPosting, SeniorityLevel, Skill
from backend.services.matcher import SemanticMatcher
from backend.tasks.db import get_sync_engine

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="match_profile", max_retries=2)
def match_profile(
    self,
    profile_id: str,
    threshold: float = 0.65,
    top_k: int = 20,
):
    """Match a profile against all stored jobs synchronously."""
    logger.info("Task match_profile: profile_id='%s'", profile_id)

    engine = get_sync_engine()
    try:
        with SASession(engine) as db:
            # Load profile
            orm_profile = db.execute(
                select(ProfileModel).where(ProfileModel.id == profile_id)
            ).scalar_one_or_none()

            if not orm_profile:
                return {"status": "error", "message": "Profile not found"}

            profile = CandidateProfile(
                full_name=orm_profile.full_name,
                email=orm_profile.email,
                raw_text=orm_profile.raw_text or "",
                skills=[Skill(**s) for s in (orm_profile.skills or [])],
                experiences=[Experience(**e) for e in (orm_profile.experiences or [])],
                education=[Education(**e) for e in (orm_profile.education or [])],
                years_of_experience=orm_profile.years_of_experience,
                seniority=SeniorityLevel(orm_profile.seniority),
                remote_preferred=orm_profile.remote_preferred,
            )

            # Load jobs
            orm_jobs = db.execute(
                select(JobModel).order_by(JobModel.created_at.desc()).limit(100)
            ).scalars().all()

            jobs = [
                JobPosting(
                    id=j.id, title=j.title, company=j.company,
                    location=j.location, description=j.description or "",
                    url=j.url, source=j.source,
                    salary_range=j.salary_range, remote=j.remote,
                    skills_required=j.skills_required or [],
                    seniority=SeniorityLevel(j.seniority) if j.seniority else SeniorityLevel.UNKNOWN,
                )
                for j in orm_jobs
            ]

            # Match
            matcher = SemanticMatcher(threshold=threshold)
            results = matcher.rank(profile, jobs, top_k=top_k)

            # Store results
            saved = 0
            for r in results:
                app = ApplicationModel(
                    profile_id=profile_id,
                    job_id=r.job.id,
                    match_score=r.score,
                    status=ApplicationStatus.MATCHED.value if r.passed_threshold else ApplicationStatus.PENDING.value,
                    skill_overlap=r.skill_overlap,
                    skill_gaps=r.skill_gaps,
                )
                db.add(app)
                saved += 1

            db.commit()

            return {
                "status": "completed",
                "total_jobs": len(jobs),
                "matched": saved,
                "passed_threshold": sum(1 for r in results if r.passed_threshold),
            }
    except Exception as e:
        logger.error("Matching task failed: %s", e)
        raise self.retry(exc=e, countdown=30)
