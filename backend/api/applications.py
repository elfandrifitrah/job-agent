"""
API router for application tracking — CRUD, status updates, history.
Uses StorageBackend for database-agnostic operation.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.models.profile import ApplicationStatus
from backend.storage.backend import StorageBackend
from backend.storage.deps import get_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/applications", tags=["applications"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class ApplicationResponse(BaseModel):
    id: str
    profile_id: str
    job_id: str
    job_title: str = ""
    company: str = ""
    match_score: float = 0.0
    status: str
    skill_overlap: list = []
    skill_gaps: list = []
    ats_name: str = ""
    fields_filled: int = 0
    total_fields: int = 0
    cover_letter_path: Optional[str] = None
    submitted_at: Optional[str] = None
    created_at: str = ""


class StatusUpdateRequest(BaseModel):
    status: str


class ApplicationStats(BaseModel):
    total: int = 0
    by_status: dict = {}
    total_matches: int = 0
    avg_match_score: float = 0.0


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("", response_model=list[ApplicationResponse])
async def list_applications(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    profile_id: Optional[str] = Query(None, description="Filter by profile"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    storage: StorageBackend = Depends(get_backend),
):
    """List applications with optional filters."""
    apps = await storage.list_applications(
        limit=limit, offset=offset, status=status_filter, profile_id=profile_id
    )

    return [
        ApplicationResponse(
            id=a.get("id", ""),
            profile_id=a.get("profile_id", ""),
            job_id=a.get("job_id", ""),
            job_title=a.get("job_title", ""),
            company=a.get("company", ""),
            match_score=a.get("match_score", 0.0) or 0.0,
            status=a.get("status", "pending"),
            skill_overlap=a.get("skill_overlap", []),
            skill_gaps=a.get("skill_gaps", []),
            ats_name=a.get("ats_name", ""),
            fields_filled=a.get("fields_filled", 0) or 0,
            total_fields=a.get("total_fields", 0) or 0,
            cover_letter_path=a.get("cover_letter_path"),
            submitted_at=a.get("submitted_at"),
            created_at=a.get("created_at", ""),
        )
        for a in apps
    ]


@router.get("/stats", response_model=ApplicationStats)
async def application_stats(storage: StorageBackend = Depends(get_backend)):
    """Aggregated application statistics."""
    stats = await storage.get_stats()
    by_status = await storage.count_applications_by_status()

    return ApplicationStats(
        total=stats.total_applications,
        by_status=by_status,
        total_matches=by_status.get("submitted", 0),
        avg_match_score=round(stats.avg_match_score, 3),
    )


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_application(app_id: str, storage: StorageBackend = Depends(get_backend)):
    """Get full application details by ID."""
    app = await storage.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    return ApplicationResponse(
        id=app.get("id", ""),
        profile_id=app.get("profile_id", ""),
        job_id=app.get("job_id", ""),
        job_title=app.get("job_title", ""),
        company=app.get("company", ""),
        match_score=app.get("match_score", 0.0) or 0.0,
        status=app.get("status", "pending"),
        skill_overlap=app.get("skill_overlap", []),
        skill_gaps=app.get("skill_gaps", []),
        ats_name=app.get("ats_name", ""),
        fields_filled=app.get("fields_filled", 0) or 0,
        total_fields=app.get("total_fields", 0) or 0,
        cover_letter_path=app.get("cover_letter_path"),
        submitted_at=app.get("submitted_at"),
        created_at=app.get("created_at", ""),
    )


@router.patch("/{app_id}/status")
async def update_application_status(
    app_id: str,
    req: StatusUpdateRequest,
    storage: StorageBackend = Depends(get_backend),
):
    """Update the status of an application."""
    if req.status not in [s.value for s in ApplicationStatus]:
        raise HTTPException(status_code=400, detail=f"Invalid status: {req.status}")

    updated = await storage.update_application_status(app_id, req.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Application not found")

    return {"id": app_id, "status": req.status, "message": "Status updated"}


@router.delete("/{app_id}", status_code=204)
async def delete_application(app_id: str, storage: StorageBackend = Depends(get_backend)):
    """Delete an application record."""
    deleted = await storage.delete_application(app_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Application not found")
