"""
API router for job posting management and discovery.
Uses StorageBackend for database-agnostic operation.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.storage.backend import StorageBackend
from backend.storage.deps import get_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class JobResponse(BaseModel):
    id: str
    title: str
    company: str
    location: str
    url: str
    source: str
    salary_range: Optional[str] = None
    remote: bool
    seniority: str
    skills_required: list
    posted_date: Optional[str] = None
    application_count: int = 0


class JobDetailResponse(JobResponse):
    description: str


class DiscoverRequest(BaseModel):
    role: str = "Software Engineer"
    location: str = ""
    remote: bool = False
    limit: int = 10
    days_old: int = 14


class DiscoverResponse(BaseModel):
    jobs: list
    sources: dict
    total: int


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("", response_model=list[JobResponse])
async def list_jobs(
    source: Optional[str] = Query(None, description="Filter by source"),
    seniority: Optional[str] = Query(None, description="Filter by seniority"),
    remote: Optional[bool] = Query(None, description="Filter remote only"),
    search: Optional[str] = Query(None, description="Search in title/company"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    storage: StorageBackend = Depends(get_backend),
):
    """List discovered job postings with optional filters."""
    jobs = await storage.list_jobs(limit=limit, offset=offset)
    # Filter in-memory for now — basic implementation
    if source:
        jobs = [j for j in jobs if j.get("source") == source]
    if seniority:
        jobs = [j for j in jobs if j.get("seniority") == seniority]
    if remote is not None:
        jobs = [j for j in jobs if j.get("remote") == remote]
    if search:
        sl = search.lower()
        jobs = [
            j for j in jobs
            if sl in (j.get("title", "") or "").lower()
            or sl in (j.get("company", "") or "").lower()
        ]

    return [
        JobResponse(
            id=j.get("id", ""),
            title=j.get("title", ""),
            company=j.get("company", ""),
            location=j.get("location", ""),
            url=j.get("url", ""),
            source=j.get("source", ""),
            salary_range=j.get("salary_range"),
            remote=j.get("remote", False) or False,
            seniority=j.get("seniority", "unknown"),
            skills_required=j.get("skills_required", []) or [],
            posted_date=j.get("posted_date"),
            application_count=0,  # Basic: no app count for JSON fallback
        )
        for j in jobs
    ]


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: str, storage: StorageBackend = Depends(get_backend)):
    """Get full job details by ID."""
    j = await storage.get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobDetailResponse(
        id=j.get("id", ""),
        title=j.get("title", ""),
        company=j.get("company", ""),
        location=j.get("location", ""),
        description=j.get("description", ""),
        url=j.get("url", ""),
        source=j.get("source", ""),
        salary_range=j.get("salary_range"),
        remote=j.get("remote", False) or False,
        seniority=j.get("seniority", "unknown"),
        skills_required=j.get("skills_required", []) or [],
        posted_date=j.get("posted_date"),
        application_count=0,
    )


@router.post("/discover", response_model=DiscoverResponse)
async def discover_jobs(
    req: DiscoverRequest,
    storage: StorageBackend = Depends(get_backend),
):
    """Discover jobs from multiple sources and store them."""
    from backend.services.job_discovery import JobDiscovery, SearchParams

    params = SearchParams(
        role=req.role,
        location=req.location,
        remote=req.remote,
        max_results=req.limit,
        days_old=req.days_old,
    )

    discovery = JobDiscovery()
    result = discovery.search(params)

    job_dicts = [job.model_dump(mode="json") for job in result.jobs]
    await storage.store_jobs(job_dicts)

    return DiscoverResponse(
        jobs=job_dicts,
        sources=result.source_counts,
        total=len(result.jobs),
    )


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str, storage: StorageBackend = Depends(get_backend)):
    """Delete a job posting."""
    deleted = await storage.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
