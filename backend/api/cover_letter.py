"""
API router for cover letter generation.
"""

from __future__ import annotations

import logging
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models.db_models import JobModel, ProfileModel
from backend.models.profile import CandidateProfile, Education, Experience, JobPosting, SeniorityLevel, Skill

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


@router.post("/generate")
async def generate_cover_letter(
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate a tailored cover letter for a profile + job combination."""
    # ─── Load profile (from DB or raw_text) ─────────────────────────────────
    from backend.services.cover_letter_generator import CoverLetterGenerator

    generator = CoverLetterGenerator()

    is_local = req.profile_id == "local" or not req.profile_id

    if is_local and req.raw_text:
        # Stateless mode: build temp profile from raw text
        profile = CandidateProfile(raw_text=req.raw_text, full_name="Candidate")
        # Try to find job from DB
        orm_job = None
        if req.job_id:
            result = await db.execute(select(JobModel).where(JobModel.id == req.job_id))
            orm_job = result.scalar_one_or_none()
    else:
        # Legacy mode: load profile from DB
        result = await db.execute(select(ProfileModel).where(ProfileModel.id == req.profile_id))
        orm_profile = result.scalar_one_or_none()
        if not orm_profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        result = await db.execute(select(JobModel).where(JobModel.id == req.job_id))
        orm_job = result.scalar_one_or_none()
        if not orm_job:
            raise HTTPException(status_code=404, detail="Job not found")

        profile = CandidateProfile(
            full_name=orm_profile.full_name or "",
            email=orm_profile.email or "",
            phone=orm_profile.phone or "",
            location=orm_profile.location or "",
            linkedin_url=orm_profile.linkedin_url or "",
            github_url=orm_profile.github_url or "",
            portfolio_url=orm_profile.portfolio_url or "",
            raw_text=orm_profile.raw_text or "",
            skills=[Skill(**s) for s in (orm_profile.skills or [])],
            experiences=[Experience(**e) for e in (orm_profile.experiences or [])],
            education=[Education(**e) for e in (orm_profile.education or [])],
            years_of_experience=orm_profile.years_of_experience or 0.0,
            seniority=SeniorityLevel(orm_profile.seniority) if orm_profile.seniority else SeniorityLevel.UNKNOWN,
            target_roles=orm_profile.target_roles or [],
            preferred_locations=orm_profile.preferred_locations or [],
            remote_preferred=orm_profile.remote_preferred or False,
        )

    # Build job posting (from DB or basic)
    if orm_job:
        job = JobPosting(
            id=orm_job.id,
            title=orm_job.title or "",
            company=orm_job.company or "",
            location=orm_job.location or "",
            description=orm_job.description or "",
            url=orm_job.url or "",
            source=orm_job.source or "",
            salary_range=orm_job.salary_range,
            remote=orm_job.remote or False,
            posted_date=orm_job.posted_date,
            skills_required=orm_job.skills_required or [],
            seniority=SeniorityLevel(orm_job.seniority) if orm_job.seniority else SeniorityLevel.UNKNOWN,
        )
    else:
        job = JobPosting(title="Position", company="Company", description="")

    # ─── Generate the cover letter ─────────────────────────────────────────
    try:
        letter = generator.generate(profile=profile, job=job, match=None, tone=req.tone)

        word_count = len(letter.split())
        character_count = len(letter)

        letter_path = ""
        if not is_local:
            # Legacy mode: save to file
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
