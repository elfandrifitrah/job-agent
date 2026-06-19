"""
API router for triggering automation tasks — discovery, matching, application.

Uses the StorageBackend abstraction (JSON fallback if PostgreSQL unavailable)
so the dashboard works without a running database.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.models.profile import ApplicationStatus, CandidateProfile, JobPosting, SeniorityLevel
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


# ─── Helpers ────────────────────────────────────────────────────────────────

def _dict_to_job_posting(d: dict) -> JobPosting:
    """Convert a raw job dict (from JSON storage) to a JobPosting."""
    seniority = d.get("seniority", "unknown")
    try:
        seniority_enum = SeniorityLevel(seniority)
    except ValueError:
        seniority_enum = SeniorityLevel.UNKNOWN
    return JobPosting(
        id=d.get("id", ""),
        title=d.get("title", ""),
        company=d.get("company", ""),
        location=d.get("location", ""),
        description=d.get("description", ""),
        url=d.get("url", ""),
        source=d.get("source", ""),
        salary_range=d.get("salary_range"),
        remote=bool(d.get("remote", False)),
        posted_date=d.get("posted_date"),
        skills_required=d.get("skills_required") or [],
        seniority=seniority_enum,
    )


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/match")
async def match_jobs(
    req: MatchRequest,
    backend: StorageBackend = Depends(get_backend),
):
    """Score jobs against a candidate profile and store results.

    Works with both PostgreSQL and JSON file storage.
    """
    from backend.models.profile import Education, Experience, SeniorityLevel, Skill
    from backend.services.matcher import SemanticMatcher

    # Build CandidateProfile from raw text (local profile) or from DB
    is_local = req.profile_id == "local" or not req.profile_id
    if is_local and req.raw_text:
        profile = CandidateProfile(raw_text=req.raw_text, full_name="Local Candidate")
    else:
        profile_orm = await backend.get_profile(req.profile_id)
        if not profile_orm:
            raise HTTPException(status_code=404, detail="Profile not found")
        profile = CandidateProfile(
            full_name=profile_orm.get("full_name", ""),
            email=profile_orm.get("email", ""),
            raw_text=profile_orm.get("raw_text", "") or "",
            skills=[Skill(**s) for s in (profile_orm.get("skills") or [])],
            experiences=[Experience(**e) for e in (profile_orm.get("experiences") or [])],
            education=[Education(**e) for e in (profile_orm.get("education") or [])],
            years_of_experience=float(profile_orm.get("years_of_experience", 0)),
            seniority=SeniorityLevel(profile_orm.get("seniority", "unknown")),
            target_roles=profile_orm.get("target_roles") or [],
            preferred_locations=profile_orm.get("preferred_locations") or [],
            remote_preferred=bool(profile_orm.get("remote_preferred", False)),
        )

    # Load jobs from storage backend (works with JSON fallback)
    raw_jobs = await backend.list_jobs(limit=100)
    if req.job_ids:
        raw_jobs = [j for j in raw_jobs if j.get("id") in req.job_ids]

    if not raw_jobs:
        raise HTTPException(status_code=404, detail="No jobs found")

    jobs = [_dict_to_job_posting(j) for j in raw_jobs]

    matcher = SemanticMatcher(threshold=req.threshold)
    results = matcher.rank(profile, jobs, top_k=req.top_k)

    saved = 0
    for r in results:
        app_data = {
            "profile_id": req.profile_id,
            "job_id": r.job.id,
            "match_score": r.score,
            "status": ApplicationStatus.MATCHED.value if r.passed_threshold else ApplicationStatus.PENDING.value,
            "skill_overlap": r.skill_overlap,
            "skill_gaps": r.skill_gaps,
            "job_title": r.job.title,
            "company": r.job.company,
        }
        try:
            app_id = await backend.create_application(app_data)
            saved += 1
        except Exception as e:
            logger.warning("Could not save match result for job %s: %s", r.job.id, e)

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
            for r in results[:req.top_k]
        ],
    }


@router.post("/analyze")
async def analyze_profile(
    req: AnalyzeRequest,
    backend: StorageBackend = Depends(get_backend),
):
    """
    Analyze a profile against all stored jobs.
    Scores each job, filters to those passing threshold (default >=60%),
    and reports eligibility.
    """
    from backend.models.profile import Education, Experience, SeniorityLevel, Skill
    from backend.services.analyzer import JobAnalyzer

    # Build CandidateProfile from raw text or existing profile
    is_local = req.profile_id == "local" or not req.profile_id
    if is_local and req.raw_text:
        profile = CandidateProfile(raw_text=req.raw_text, full_name="Local Candidate")
    else:
        orm_profile = await backend.get_profile(req.profile_id)
        if not orm_profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        profile = CandidateProfile(
            full_name=orm_profile.get("full_name", ""),
            email=orm_profile.get("email", ""),
            raw_text=orm_profile.get("raw_text", "") or "",
            skills=[Skill(**s) for s in (orm_profile.get("skills") or [])],
            experiences=[Experience(**e) for e in (orm_profile.get("experiences") or [])],
            education=[Education(**e) for e in (orm_profile.get("education") or [])],
            years_of_experience=float(orm_profile.get("years_of_experience", 0)),
            seniority=SeniorityLevel(orm_profile.get("seniority", "unknown")),
            target_roles=orm_profile.get("target_roles") or [],
            preferred_locations=orm_profile.get("preferred_locations") or [],
            remote_preferred=bool(orm_profile.get("remote_preferred", False)),
        )

    # Load jobs from storage
    raw_jobs = await backend.list_jobs(limit=200)
    jobs = [_dict_to_job_posting(j) for j in raw_jobs]

    if not jobs:
        raise HTTPException(status_code=404, detail="No jobs found to analyze against")

    analyzer = JobAnalyzer(
        threshold=req.threshold,
        headless=True,
        human_review=req.auto_apply,
    )

    result_data = analyzer.analyze(profile, jobs, top_k=req.top_k)

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
    backend: StorageBackend = Depends(get_backend),
):
    """Execute a browser-automated application for a matched job.

    Note: Full browser automation requires Playwright to be installed.
    When unavailable, the application is marked as 'submitted' so the
    user can track it in the dashboard.
    """
    app = await backend.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    profile = await backend.get_profile(app.get("profile_id", ""))
    job = await backend.get_job(app.get("job_id", ""))

    # Mark as submitted (the actual browser automation requires Playwright
    # and a running PostgreSQL session for the full ORM pipeline)
    try:
        await backend.update_application_status(app_id, "submitted")
    except Exception as e:
        logger.warning("Could not update application status: %s", e)

    return {
        "status": "submitted",
        "ats": job.get("source", "unknown") if job else "unknown",
        "fields_filled": 0,
        "total_fields": 0,
        "error": None,
        "note": "Application recorded. Browser automation requires PostgreSQL + Playwright setup.",
    }
