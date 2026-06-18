"""
API router for triggering automation tasks — discovery, matching, application.
Uses StorageBackend where possible; for complex matching queries, falls back
to the async session pattern directly.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.db_models import ApplicationModel, JobModel, ProfileModel
from backend.models.profile import ApplicationStatus
from backend.storage.backend import StorageBackend
from backend.storage.deps import get_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/automation", tags=["automation"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class MatchRequest(BaseModel):
    profile_id: str = "local"
    job_ids: Optional[list[str]] = None
    raw_text: str = ""
    threshold: float = 0.65
    top_k: int = 20


class ApplyRequest(BaseModel):
    profile_id: str
    job_id: str
    cover_letter_path: Optional[str] = None
    headless: bool = True
    human_review: bool = True


class AnalyzeRequest(BaseModel):
    profile_id: str = "local"
    raw_text: str = ""
    threshold: float = 0.60
    auto_apply: bool = False
    top_k: int = 50


class BatchApplyRequest(BaseModel):
    profile_id: str
    job_ids: list[str]
    cover_letter_path: Optional[str] = None
    headless: bool = True
    human_review: bool = True


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/match")
async def match_jobs(
    req: MatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Score jobs against a candidate profile and store results.
    Requires PostgreSQL for full matching pipeline.
    Falls back gracefully if DB is unavailable.
    """
    # This endpoint uses raw SQLAlchemy because it needs complex ORM operations
    # (profile reconstruction, batch application creation)
    from backend.models.profile import CandidateProfile, Education, Experience, SeniorityLevel, Skill

    is_local = req.profile_id == "local" or not req.profile_id

    if is_local and req.raw_text:
        profile = CandidateProfile(raw_text=req.raw_text, full_name="Local Candidate")
    else:
        result = await db.execute(select(ProfileModel).where(ProfileModel.id == req.profile_id))
        orm_profile = result.scalar_one_or_none()
        if not orm_profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        profile = CandidateProfile(
            full_name=orm_profile.full_name,
            email=orm_profile.email,
            raw_text=orm_profile.raw_text or "",
            skills=[Skill(**s) for s in (orm_profile.skills or [])],
            experiences=[Experience(**e) for e in (orm_profile.experiences or [])],
            education=[Education(**e) for e in (orm_profile.education or [])],
            years_of_experience=orm_profile.years_of_experience,
            seniority=SeniorityLevel(orm_profile.seniority),
            target_roles=orm_profile.target_roles or [],
        preferred_locations=orm_profile.preferred_locations or [],
        remote_preferred=orm_profile.remote_preferred,
    )

    query = select(JobModel)
    if req.job_ids:
        query = query.where(JobModel.id.in_(req.job_ids))
    result = await db.execute(query)
    orm_jobs = result.scalars().all()

    if not orm_jobs:
        raise HTTPException(status_code=404, detail="No jobs found")

    from backend.models.profile import JobPosting
    jobs = [
        JobPosting(
            id=j.id, title=j.title, company=j.company,
            location=j.location, description=j.description or "",
            url=j.url, source=j.source,
            salary_range=j.salary_range, remote=j.remote,
            posted_date=j.posted_date,
            skills_required=j.skills_required or [],
            seniority=SeniorityLevel(j.seniority) if j.seniority else SeniorityLevel.UNKNOWN,
        )
        for j in orm_jobs
    ]

    from backend.services.matcher import SemanticMatcher
    matcher = SemanticMatcher(threshold=req.threshold)
    results = matcher.rank(profile, jobs, top_k=req.top_k)

    saved = 0
    for r in results:
        app = ApplicationModel(
            profile_id=req.profile_id,
            job_id=r.job.id,
            match_score=r.score,
            status=ApplicationStatus.MATCHED.value if r.passed_threshold else ApplicationStatus.PENDING.value,
            skill_overlap=r.skill_overlap,
            skill_gaps=r.skill_gaps,
        )
        db.add(app)
        saved += 1

    await db.flush()

    return {
        "matched": saved,
        "passed_threshold": sum(1 for r in results if r.passed_threshold),
        "results": [
            {
                "job_id": r.job.id,
                "job_title": r.job.title,
                "company": r.job.company,
                "score": r.score,
                "passed_threshold": r.passed_threshold,
                "skill_overlap": r.skill_overlap[:8],
                "skill_gaps": r.skill_gaps[:8],
            }
            for r in results[:10]
        ],
    }


@router.post("/analyze")
async def analyze_profile(
    req: "AnalyzeRequest",
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze a profile against all stored jobs.
    Scores each job, filters to those passing threshold (default ≥60%),
    and reports eligibility for auto-application.
    """
    from backend.models.profile import CandidateProfile, Education, Experience, SeniorityLevel, Skill

    is_local = req.profile_id == "local" or not req.profile_id

    if is_local and req.raw_text:
        profile = CandidateProfile(raw_text=req.raw_text, full_name="Local Candidate")
    else:
        result = await db.execute(select(ProfileModel).where(ProfileModel.id == req.profile_id))
        orm_profile = result.scalar_one_or_none()
        if not orm_profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        profile = CandidateProfile(
            full_name=orm_profile.full_name,
            email=orm_profile.email,
            raw_text=orm_profile.raw_text or "",
            skills=[Skill(**s) for s in (orm_profile.skills or [])],
            experiences=[Experience(**e) for e in (orm_profile.experiences or [])],
            education=[Education(**e) for e in (orm_profile.education or [])],
            years_of_experience=orm_profile.years_of_experience,
            seniority=SeniorityLevel(orm_profile.seniority),
            target_roles=orm_profile.target_roles or [],
            preferred_locations=orm_profile.preferred_locations or [],
            remote_preferred=orm_profile.remote_preferred,
        )

    from backend.services.analyzer import JobAnalyzer

    analyzer = JobAnalyzer(
        threshold=req.threshold,
        headless=True,
        human_review=req.auto_apply,
    )

    jobs = await JobAnalyzer.load_jobs_async(db)

    if not jobs:
        raise HTTPException(status_code=404, detail="No jobs found to analyze against")

    result_data = analyzer.analyze(profile, jobs, top_k=50)

    return {
        "profile_name": profile.full_name,
        "total_scored": result_data.total_scored,
        "eligible": result_data.eligible,
        "threshold": analyzer.threshold,
        "results": [
            {
                "job_id": item.job.id,
                "job_title": item.job.title,
                "company": item.job.company,
                "location": item.job.location,
                "url": item.job.url,
                "score": item.match.score,
                "passed_threshold": item.eligible,
                "skill_overlap": item.match.skill_overlap[:10],
                "skill_gaps": item.match.skill_gaps[:10],
                "reasoning": item.match.reasoning,
            }
            for item in result_data.items
        ],
    }


@router.post("/apply/{app_id}")
async def apply_to_job(
    app_id: str,
    req: Optional[ApplyRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Execute a browser-automated application for a matched job.
    Requires PostgreSQL for full automation pipeline.
    """
    result = await db.execute(select(ApplicationModel).where(ApplicationModel.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    result = await db.execute(select(ProfileModel).where(ProfileModel.id == app.profile_id))
    orm_profile = result.scalar_one_or_none()

    result = await db.execute(select(JobModel).where(JobModel.id == app.job_id))
    orm_job = result.scalar_one_or_none()

    if not orm_profile or not orm_job or not orm_job.url:
        raise HTTPException(status_code=400, detail="Missing profile, job, or URL")

    from backend.models.profile import CandidateProfile, Education, Experience, SeniorityLevel, Skill

    profile = CandidateProfile(
        full_name=orm_profile.full_name,
        email=orm_profile.email,
        phone=orm_profile.phone,
        location=orm_profile.location,
        linkedin_url=orm_profile.linkedin_url,
        github_url=orm_profile.github_url,
        portfolio_url=orm_profile.portfolio_url,
        raw_text=orm_profile.raw_text or "",
        skills=[Skill(**s) for s in (orm_profile.skills or [])],
        experiences=[Experience(**e) for e in (orm_profile.experiences or [])],
        education=[Education(**e) for e in (orm_profile.education or [])],
        years_of_experience=orm_profile.years_of_experience,
        seniority=SeniorityLevel(orm_profile.seniority),
        remote_preferred=orm_profile.remote_preferred,
    )

    from backend.services.browser_automation import BrowserAutomation

    headless = req.headless if req else True
    human_review = req.human_review if req else True

    automator = BrowserAutomation(
        profile=profile,
        cv_path="",
        cover_letter_path=req.cover_letter_path if req else "",
        headless=headless,
        human_review=human_review,
    )

    try:
        automator.launch()
        result = automator.apply(url=orm_job.url, use_ats_adapter=True)

        app.status = result.status
        app.ats_name = result.ats
        app.fields_filled = result.fields_filled
        app.total_fields = result.total_fields
        app.screenshot_path = result.screenshot_path
        if result.status == "submitted":
            from datetime import UTC, datetime
            app.submitted_at = datetime.now(UTC)
        if result.error_message:
            app.error_log = result.error_message[:1000]
        await db.flush()

        return {
            "status": result.status,
            "ats": result.ats,
            "fields_filled": result.fields_filled,
            "total_fields": result.total_fields,
            "error": result.error_message,
        }
    finally:
        automator.close()
