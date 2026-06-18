"""
API router for dashboard — aggregated stats, charts data, health checks.
Uses StorageBackend for database-agnostic operation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.database import check_db
from backend.storage.backend import StorageBackend
from backend.storage.deps import get_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_profiles: int = 0
    total_jobs: int = 0
    total_applications: int = 0
    submitted_applications: int = 0
    failed_applications: int = 0
    captcha_blocked: int = 0
    avg_match_score: float = 0.0
    jobs_by_source: dict = {}
    applications_today: int = 0
    database_connected: bool = False


class SourceBreakdown(BaseModel):
    source: str
    count: int


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(storage: StorageBackend = Depends(get_backend)):
    """Aggregated dashboard statistics."""
    db_ok = await check_db()
    stats = await storage.get_stats()

    # Enrich with additional breakdowns
    sources = await storage.count_jobs_by_source()
    by_status = await storage.count_applications_by_status()

    return DashboardStats(
        total_profiles=stats.total_profiles,
        total_jobs=stats.total_jobs,
        total_applications=stats.total_applications,
        submitted_applications=stats.submitted_applications,
        failed_applications=by_status.get("error", 0),
        captcha_blocked=by_status.get("captcha_blocked", 0),
        avg_match_score=round(stats.avg_match_score, 3),
        jobs_by_source={s.source: s.count for s in sources},
        applications_today=stats.applications_today,
        database_connected=db_ok,
    )


@router.get("/sources")
async def get_source_breakdown(storage: StorageBackend = Depends(get_backend)):
    """Job discovery source breakdown."""
    sources = await storage.count_jobs_by_source()
    return [{"source": s.source, "count": s.count} for s in sources]


@router.get("/health")
async def dashboard_health():
    """Lightweight health status for the dashboard."""
    db_ok = await check_db()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "timestamp": datetime.now(UTC).isoformat(),
    }
