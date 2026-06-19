"""
API router for candidate profile management.
Uses StorageBackend for database-agnostic operation.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from backend.models.profile import CandidateProfile
from backend.storage.backend import StorageBackend
from backend.storage.deps import get_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class ProfileResponse(BaseModel):
    id: str
    full_name: str
    email: str
    phone: str
    location: str
    linkedin_url: str
    github_url: str
    years_of_experience: float
    seniority: str
    remote_preferred: bool
    skills_count: int
    experiences_count: int
    parsed_at: Optional[str] = None
    source_file: str


class ProfileDetailResponse(ProfileResponse):
    raw_text: str = ""
    skills: list = []
    experiences: list = []
    education: list = []
    target_roles: list = []
    preferred_locations: list = []


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("", response_model=list[ProfileResponse])
async def list_profiles(storage: StorageBackend = Depends(get_backend)):
    """List all parsed CV profiles."""
    profiles = await storage.list_profiles()
    return [
        ProfileResponse(
            id=p.get("id", ""),
            full_name=p.get("full_name", ""),
            email=p.get("email", ""),
            phone=p.get("phone", ""),
            location=p.get("location", ""),
            linkedin_url=p.get("linkedin_url", ""),
            github_url=p.get("github_url", ""),
            years_of_experience=p.get("years_of_experience", 0.0) or 0.0,
            seniority=p.get("seniority", "unknown"),
            remote_preferred=p.get("remote_preferred", False) or False,
            skills_count=p.get("skills_count", 0),
            experiences_count=p.get("experiences_count", 0),
            parsed_at=p.get("parsed_at"),
            source_file=p.get("source_file", ""),
        )
        for p in profiles
    ]


@router.get("/{profile_id}", response_model=ProfileDetailResponse)
async def get_profile(profile_id: str, storage: StorageBackend = Depends(get_backend)):
    """Get full profile details by ID."""
    p = await storage.get_profile(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")

    return ProfileDetailResponse(
        id=p.get("id", ""),
        full_name=p.get("full_name", ""),
        email=p.get("email", ""),
        phone=p.get("phone", ""),
        location=p.get("location", ""),
        linkedin_url=p.get("linkedin_url", ""),
        github_url=p.get("github_url", ""),
        years_of_experience=p.get("years_of_experience", 0.0) or 0.0,
        seniority=p.get("seniority", "unknown"),
        remote_preferred=p.get("remote_preferred", False) or False,            skills_count=p.get("skills_count", 0),
            experiences_count=p.get("experiences_count", 0),
        parsed_at=p.get("parsed_at"),
        source_file=p.get("source_file", ""),
        raw_text=p.get("raw_text", ""),
        skills=p.get("skills", []) or [],
        experiences=p.get("experiences", []) or [],
        education=p.get("education", []) or [],
        target_roles=p.get("target_roles", []) or [],
        preferred_locations=p.get("preferred_locations", []) or [],
    )


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, storage: StorageBackend = Depends(get_backend)):
    """Delete a profile and all associated applications."""
    deleted = await storage.delete_profile(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")


@router.post("/parse")
async def parse_cv(
    file: UploadFile = File(...),
    storage: StorageBackend = Depends(get_backend),
):
    """Upload and parse a CV file."""
    from backend.services.cv_parser import CVParser

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
    import tempfile
    from pathlib import Path

    # Validate file extension
    suffix = Path(file.filename).suffix.lower() if file.filename else ""
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: PDF, DOCX, TXT.",
        )

    # Validate content type (basic check — not foolproof but raises the bar)
    content_type = file.content_type or ""
    allowed_ct = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "text/plain",
    }
    if content_type and content_type not in allowed_ct:
        # Some clients send wrong content types; log but allow if extension is ok
        logger.warning("Unexpected content type %s for file %s", content_type, file.filename)

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large ({len(content) // 1024 // 1024}MB). Maximum is 10MB.")

    # Validate magic bytes for PDF
    if suffix == ".pdf" and not content[:4] == b"%PDF":
        raise HTTPException(status_code=400, detail="File appears not to be a valid PDF.")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        parser = CVParser()
        profile = parser.parse(tmp_path)

        # Store via repository
        profile_dict = profile.model_dump(mode="json")
        profile_id = await storage.create_profile(profile_dict)

        return {
            "id": profile_id,
            "full_name": profile.full_name,
            "email": profile.email,
            "skills": [s.name for s in profile.skills[:15]],
            "seniority": profile.seniority.value,
            "years_experience": profile.years_of_experience,
            "message": "Profile parsed and saved",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("CV parse failed: %s", type(e).__name__)
        raise HTTPException(status_code=400, detail="Failed to parse CV. Ensure the file is a valid PDF, DOCX, or TXT.")
    finally:
        import os
        os.unlink(tmp_path)


@router.post("")
async def create_profile_manual(
    profile: CandidateProfile,
    storage: StorageBackend = Depends(get_backend),
):
    """Manually create a candidate profile (without parsing a CV)."""
    profile_id = await storage.create_profile(profile.model_dump(mode="json"))
    return {"id": profile_id, "message": "Profile created"}
