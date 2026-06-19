"""
API router for cover letter generation.
"""

from __future__ import annotations

import logging
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.models.profile import CandidateProfile, Education, Experience, JobPosting, SeniorityLevel, Skill
from backend.storage.backend import StorageBackend
from backend.storage.deps import get_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cover-letter", tags=["cover-letter"])


# ─── Schemas ────────────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    profile_id: str = "local"
    job_id: str = ""
    raw_text: str = ""
    tone: str = "professional"


class GenerateResponse(BaseModel):
    letter_text: str
    letter_path: str = ""
    character_count: int
    word_count: int


# ─── Endpoints ──────────────────────────────────────────────────────────────


def _dict_to_job_posting(j: dict | None) -> JobPosting:
    if not j:
        return JobPosting(title="Position", company="Company", description="")
    seniority = j.get("seniority", "unknown")
    try:
        seniority_enum = SeniorityLevel(seniority)
    except ValueError:
        seniority_enum = SeniorityLevel.UNKNOWN
    return JobPosting(
        id=j.get("id", ""),
        title=j.get("title", ""),
        company=j.get("company", ""),
        location=j.get("location", ""),
        description=j.get("description", ""),
        url=j.get("url", ""),
        source=j.get("source", ""),
        salary_range=j.get("salary_range"),
        remote=bool(j.get("remote", False)),
        posted_date=j.get("posted_date"),
        skills_required=j.get("skills_required") or [],
        seniority=seniority_enum,
    )


@router.post("/generate")
async def generate_cover_letter(
    req: GenerateRequest,
    backend: StorageBackend = Depends(get_backend),
):
    """Generate a tailored cover letter for a profile + job combination."""
    from backend.services.cover_letter_generator import CoverLetterGenerator

    generator = CoverLetterGenerator()

    is_local = req.profile_id == "local" or not req.profile_id

    profile = None
    job = None

    if is_local and req.raw_text:
        profile = CandidateProfile(raw_text=req.raw_text, full_name="Candidate")
        if req.job_id:
            raw_job = await backend.get_job(req.job_id)
            job = _dict_to_job_posting(raw_job)
    else:
        raw_profile = await backend.get_profile(req.profile_id)
        if not raw_profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        profile = CandidateProfile(
            full_name=raw_profile.get("full_name") or "",
            email=raw_profile.get("email") or "",
            phone=raw_profile.get("phone") or "",
            location=raw_profile.get("location") or "",
            linkedin_url=raw_profile.get("linkedin_url") or "",
            github_url=raw_profile.get("github_url") or "",
            portfolio_url=raw_profile.get("portfolio_url") or "",
            raw_text=raw_profile.get("raw_text") or "",
            skills=[Skill(**s) for s in (raw_profile.get("skills") or [])],
            experiences=[Experience(**e) for e in (raw_profile.get("experiences") or [])],
            education=[Education(**e) for e in (raw_profile.get("education") or [])],
            years_of_experience=float(raw_profile.get("years_of_experience", 0)),
            seniority=SeniorityLevel(raw_profile.get("seniority", "unknown")),
            target_roles=raw_profile.get("target_roles") or [],
            preferred_locations=raw_profile.get("preferred_locations") or [],
            remote_preferred=bool(raw_profile.get("remote_preferred", False)),
        )
        raw_job = await backend.get_job(req.job_id) if req.job_id else None
        job = _dict_to_job_posting(raw_job) if raw_job else JobPosting(title="Position", company="Company", description="")

    if profile is None:
        raise HTTPException(status_code=400, detail="Could not build profile")
    if job is None:
        job = JobPosting(title="Position", company="Company", description="")

    try:
        letter = generator.generate(profile=profile, job=job, match=None, tone=req.tone)

        word_count = len(letter.split())
        character_count = len(letter)

        letter_path = ""
        if not is_local:
            output_dir = settings.cover_letter_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", f"{job.company}_{job.title}".lower())
            safe_name = safe_name.strip("_")[:60]
            letter_path = str(output_dir / f"{safe_name}.txt")

        return GenerateResponse(
            letter_text=letter,
            letter_path=letter_path,
            character_count=character_count,
            word_count=word_count,
        )

    except Exception as e:
        logger.error("Cover letter generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Cover letter generation failed: {e}")
