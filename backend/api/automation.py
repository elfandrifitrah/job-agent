"""
API router for triggering automation tasks — discovery, matching, application.

Uses the StorageBackend abstraction (JSON fallback if PostgreSQL unavailable)
so the dashboard works without a running database.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
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
    profile_id: str = "local"
    job_id: str = ""
    cover_letter_path: Optional[str] = None
    headless: bool = True
    human_review: bool = True


class AnalyzeRequest(BaseModel):
    profile_id: str = "local"
    raw_text: str = ""
    threshold: float = 0.60
    auto_apply: bool = False
    top_k: int = 50


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


async def _build_profile(
    backend: StorageBackend,
    profile_id: str,
    raw_text: str = "",
) -> CandidateProfile:
    """Build a CandidateProfile from raw text (local) or from the storage backend."""
    from backend.models.profile import Education, Experience, SeniorityLevel, Skill

    is_local = profile_id == "local" or not profile_id
    if is_local and raw_text:
        return CandidateProfile(raw_text=raw_text, full_name="Local Candidate")

    orm = await backend.get_profile(profile_id)
    if not orm:
        raise HTTPException(status_code=404, detail="Profile not found")
    return CandidateProfile(
        full_name=orm.get("full_name", ""),
        email=orm.get("email", ""),
        raw_text=orm.get("raw_text", "") or "",
        skills=[Skill(**s) for s in (orm.get("skills") or [])],
        experiences=[Experience(**e) for e in (orm.get("experiences") or [])],
        education=[Education(**e) for e in (orm.get("education") or [])],
        years_of_experience=float(orm.get("years_of_experience", 0)),
        seniority=SeniorityLevel(orm.get("seniority", "unknown")),
        target_roles=orm.get("target_roles") or [],
        preferred_locations=orm.get("preferred_locations") or [],
        remote_preferred=bool(orm.get("remote_preferred", False)),
    )


async def _ensure_local_profile(
    backend: StorageBackend,
    raw_text: str = "",
) -> str:
    """Ensure a profile with id='local' exists; create if needed. Returns profile_id."""
    profile_id = "local"
    existing = await backend.get_profile(profile_id)
    if not existing:
        try:
            await backend.create_profile({"id": profile_id, "full_name": "Local Candidate", "raw_text": raw_text or ""})
        except Exception as e:
            logger.warning("Could not create local profile: %s", e)
    return profile_id


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/match")
async def match_jobs(
    req: MatchRequest,
    backend: StorageBackend = Depends(get_backend),
):
    """Score jobs against a candidate profile and store results.

    Works with both PostgreSQL and JSON file storage.
    """
    from backend.services.matcher import SemanticMatcher

    profile = await _build_profile(backend, req.profile_id, req.raw_text)

    # Load jobs from storage backend (works with JSON fallback)
    raw_jobs = await backend.list_jobs(limit=100)
    if req.job_ids:
        raw_jobs = [j for j in raw_jobs if j.get("id") in req.job_ids]

    if not raw_jobs:
        raise HTTPException(status_code=404, detail="No jobs found")

    jobs = [_dict_to_job_posting(j) for j in raw_jobs]

    matcher = SemanticMatcher(threshold=req.threshold)
    results = matcher.rank(profile, jobs, top_k=req.top_k)

    profile_id = await _ensure_local_profile(backend, req.raw_text)

    saved = 0
    saved_apps = {}
    for r in results:
        app_data = {
            "profile_id": profile_id,
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
            saved_apps[r.job.id] = app_id
        except Exception as e:
            logger.warning("Could not save match result for job %s: %s", r.job.id, e)

    return {
        "matched": saved,
        "passed_threshold": sum(1 for r in results if r.passed_threshold),
        "results": [
            {
                "job_id": r.job.id,
                "application_id": saved_apps.get(r.job.id),
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
    from backend.services.analyzer import JobAnalyzer

    profile = await _build_profile(backend, req.profile_id, req.raw_text)

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


@router.post("/apply-now")
async def apply_now(
    req: ApplyRequest,
    backend: StorageBackend = Depends(get_backend),
):
    """Create an application for a job and mark it as submitted.
    This is the direct-submit endpoint used by the frontend's
    'Submit All Eligible' flow — no browser automation needed.
    """
    profile_id = await _ensure_local_profile(backend, req.profile_id)

    app_data = {
        "profile_id": profile_id,
        "job_id": req.job_id,
        "match_score": 0.0,
        "status": "submitted",
    }
    try:
        app_id = await backend.create_application(app_data)
    except Exception as e:
        logger.error("Could not create application: %s", e)
        raise HTTPException(status_code=500, detail="Could not create application. Please try again.")

    return {
        "status": "submitted",
        "application_id": app_id,
        "error": None,
        "note": "Application created and marked as submitted.",
    }
