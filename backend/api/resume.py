"""
API router for Resume Tailoring — rewrite bullet points per job and generate PDF.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import settings
from backend.database import storage as json_storage
from backend.models.profile import CandidateProfile, JobPosting, MatchResult
from backend.services.resume_tailor import tailor_resume

TAILORED_DIR = settings.data_dir / "tailored_resumes"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resume", tags=["resume"])


class TailorRequest(BaseModel):
    profile_id: str
    job_id: str


class TailorResponse(BaseModel):
    success: bool
    pdf_path: str = ""
    message: str = ""


class DownloadRequest(BaseModel):
    path: str


@router.post("/tailor", response_model=TailorResponse)
async def tailor(req: TailorRequest):
    """Rewrite resume bullet points for a specific job and generate tailored PDF."""
    # Load profile
    profiles = json_storage.get_profiles()
    profile_data = None
    for p in profiles:
        if p.get("id") == req.profile_id:
            profile_data = p
            break
    if not profile_data:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile = CandidateProfile(**profile_data)

    # Load job
    jobs = json_storage.get_jobs()
    job_data = None
    for j in jobs:
        if j.get("id") == req.job_id:
            job_data = j
            break
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")

    job = JobPosting(**job_data)

    # Create a quick match result to pass skill overlap info
    cv_skills = set(s.lower() for s in profile.skill_names)
    job_skills = set(s.lower() for s in job.skills_required)
    overlap = sorted(cv_skills & job_skills)
    gap = sorted(job_skills - cv_skills)

    match = MatchResult(
        job=job,
        score=0.0,  # Not needed for tailoring
        skill_overlap=overlap,
        skill_gaps=gap,
        passed_threshold=True,
    )

    pdf_path = tailor_resume(profile, match)
    if not pdf_path or not Path(pdf_path).exists():
        return TailorResponse(success=False, message="Resume tailoring failed")

    return TailorResponse(
        success=True,
        pdf_path=str(pdf_path),
        message="Resume tailored successfully",
    )


@router.get("/download")
async def download_resume(path: str):
    """Download a tailored resume PDF. Path must be within the tailored_resumes directory."""
    file_path = Path(path).resolve()
    allowed = TAILORED_DIR.resolve()
    if not str(file_path).startswith(str(allowed)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=file_path.name,
    )
