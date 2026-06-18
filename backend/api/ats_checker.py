"""
API router for ATS Resume Checker — score CVs against 20+ ATS criteria.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.ats_checker import AtsChecker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ats", tags=["ats"])


class CheckRequest(BaseModel):
    cv_text: str
    job_skills: list[str] = []
    file_extension: str = ".pdf"


class CriterionResult(BaseModel):
    name: str
    passed: bool
    score: float
    detail: str = ""


class CheckResponse(BaseModel):
    keyword_match: float = 0.0
    format_score: float = 0.0
    impact_score: float = 0.0
    completeness_score: float = 0.0
    composite: int = 0
    criteria: list[CriterionResult] = []
    suggestions: list[str] = []


class ProfileCheckRequest(BaseModel):
    profile_id: str
    job_id: Optional[str] = None


@router.post("/check", response_model=CheckResponse)
async def check_cv(req: CheckRequest):
    """Score a CV against ATS criteria."""
    if not req.cv_text or len(req.cv_text.strip()) < 50:
        raise HTTPException(status_code=400, detail="CV text too short (min 50 chars)")

    checker = AtsChecker(cv_text=req.cv_text, file_extension=req.file_extension)
    result = checker.check_all(job_skills=req.job_skills)

    return CheckResponse(
        keyword_match=result.keyword_match,
        format_score=result.format_score,
        impact_score=result.impact_score,
        completeness_score=result.completeness_score,
        composite=result.composite,
        criteria=[CriterionResult(**c.model_dump()) for c in result.criteria],
        suggestions=result.suggestions,
    )


@router.post("/check-profile", response_model=CheckResponse)
async def check_cv_from_profile(req: ProfileCheckRequest):
    """Score a stored profile's CV against ATS criteria, optionally against a job."""
    from backend.database import storage as json_storage

    profiles = json_storage.get_profiles()
    profile_data = None
    for p in profiles:
        if p.get("id") == req.profile_id:
            profile_data = p
            break

    if not profile_data:
        raise HTTPException(status_code=404, detail="Profile not found")

    cv_text = profile_data.get("raw_text", "")
    if not cv_text:
        raise HTTPException(status_code=400, detail="No raw CV text in profile")

    job_skills: list[str] = []
    if req.job_id:
        jobs = json_storage.get_jobs()
        for j in jobs:
            if j.get("id") == req.job_id:
                job_skills = j.get("skills_required", [])
                break

    checker = AtsChecker(cv_text=cv_text)
    result = checker.check_all(job_skills=job_skills)

    return CheckResponse(
        keyword_match=result.keyword_match,
        format_score=result.format_score,
        impact_score=result.impact_score,
        completeness_score=result.completeness_score,
        composite=result.composite,
        criteria=[CriterionResult(**c.model_dump()) for c in result.criteria],
        suggestions=result.suggestions,
    )
