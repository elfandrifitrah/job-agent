"""
API router for live Product Manager job listings.
Multi-source: fetches from Jobicy (free, no key) + Adzuna (free tier, needs API key).
Stores results, deduplicates, and tracks source breakdown.
Runs on-demand via API or daily via APScheduler.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import storage as json_storage
from backend.storage.backend import StorageBackend
from backend.storage.deps import get_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live-jobs", tags=["live-jobs"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class LiveJobItem(BaseModel):
    id: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    source: str = ""
    salary_range: Optional[str] = None
    remote: bool = True
    posted_date: Optional[str] = None
    seniority: str = "unknown"
    skills_required: list[str] = []


class LiveSearchResponse(BaseModel):
    jobs: list[LiveJobItem] = []
    total: int = 0
    sources: dict[str, int] = {}       # source_name -> count
    searched_at: str = ""
    is_cached: bool = False


# ─── Helpers ────────────────────────────────────────────────────────────────

LIVE_JOBS_KEY = "live_jobs"
LAST_REFRESH_KEY = "live_jobs_last_refresh"
SOURCES_KEY = "live_jobs_sources"
CACHE_TTL_HOURS = 6  # Re-fetch if cache is older than 6 hours


def _get_live_jobs_data() -> dict[str, Any]:
    """Get the live jobs section from the data store."""
    data = json_storage._data  # type: ignore[attr-defined]
    if LIVE_JOBS_KEY not in data:
        data[LIVE_JOBS_KEY] = []
    if LAST_REFRESH_KEY not in data:
        data[LAST_REFRESH_KEY] = None
    if SOURCES_KEY not in data:
        data[SOURCES_KEY] = {}
    return data


def _save_live_jobs_data() -> None:
    """Persist the live jobs data section."""
    json_storage._save()  # type: ignore[attr-defined]


# ─── Multi-source search ────────────────────────────────────────────────────

def _search_source(
    source_cls: type,
    params: Any,
) -> tuple[list[dict[str, Any]], int]:
    """Run a single source search and return (job_dicts, count)."""
    source = source_cls()
    job_postings = source.search(params)
    job_dicts = [j.model_dump(mode="json") for j in job_postings]
    return job_dicts, len(job_dicts)


async def search_and_store_live_pm_jobs(
    keyword: str = "Product Manager",
    max_results: int = 50,
    days_old: int = 1,
) -> list[dict[str, Any]]:
    """Search for Product Manager remote jobs from all configured sources.

    Always queries Jobicy (free, no key needed).
    Also queries Adzuna if API keys are configured in .env.

    Deduplicates by job ID (deterministic hash) and stores merged results
    with source breakdown. Returns the deduplicated job list.
    """
    from backend.config import settings
    from backend.services.job_discovery import AdzunaSource, FirecrawlSource, JobicySource, SearchParams

    params = SearchParams(
        role=keyword,
        remote=True,
        max_results=max_results,
        days_old=days_old,
    )

    all_jobs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    source_counts: dict[str, int] = {}

    # --- Source 1: Jobicy (always available, free REST API) ---
    jobicy_jobs, jobicy_count = _search_source(JobicySource, params)
    for j in jobicy_jobs:
        jid = j.get("id", "")
        if jid and jid not in seen_ids:
            seen_ids.add(jid)
            all_jobs.append(j)
    source_counts["jobicy"] = len(jobicy_jobs)
    logger.info("Jobicy: %d jobs", jobicy_count)

    # --- Source 2: Adzuna (only if API keys are configured) ---
    if settings.adzuna_app_id and settings.adzuna_api_key:
        adzuna_jobs, adzuna_count = _search_source(AdzunaSource, params)
        for j in adzuna_jobs:
            jid = j.get("id", "")
            if jid and jid not in seen_ids:
                seen_ids.add(jid)
                # Mark with explicit source
                j["source"] = "adzuna"
                all_jobs.append(j)
        source_counts["adzuna"] = len(adzuna_jobs)
        logger.info("Adzuna: %d jobs (%d unique after dedup)", adzuna_count, len(adzuna_jobs))
    else:
        logger.info("Adzuna: not configured — skipping (set ADZUNA_APP_ID and ADZUNA_API_KEY in .env)")

    # --- Source 3: Firecrawl (free tier, no key needed for basic use) ---
    # Scrapes LinkedIn + Indeed. Uses ~2-3 pages per run (~60-90/month on free tier).
    firecrawl_jobs, firecrawl_count = _search_source(FirecrawlSource, params)
    for j in firecrawl_jobs:
        jid = j.get("id", "")
        if jid and jid not in seen_ids:
            seen_ids.add(jid)
            j["source"] = "firecrawl"
            all_jobs.append(j)
    source_counts["firecrawl"] = len(firecrawl_jobs)
    logger.info("Firecrawl: %d jobs (%d unique after dedup)", firecrawl_count, len(firecrawl_jobs))

    # --- Source 4: Company career pages (Firecrawl-based, free tier) ---
    # Scans target_companies.yaml list using Firecrawl + ATS adapters.
    try:
        from backend.services.career_page_scanner import scan_all_career_pages
        career_jobs = await scan_all_career_pages(
            role_keyword=keyword,
            max_companies=10,
        )
        for j in career_jobs:
            jid = j.get("id", "")
            if jid and jid not in seen_ids:
                seen_ids.add(jid)
                j["source"] = "career_pages"
                all_jobs.append(j)
        source_counts["career_pages"] = len(career_jobs)
        logger.info("Career pages: %d jobs from direct company scan", len(career_jobs))
    except Exception as e:
        logger.warning("Career page scan failed: %s", e)
        source_counts["career_pages"] = 0

    # --- Store merged results ---
    data = _get_live_jobs_data()
    data[LIVE_JOBS_KEY] = all_jobs
    data[LAST_REFRESH_KEY] = datetime.now(UTC).isoformat()
    data[SOURCES_KEY] = source_counts
    _save_live_jobs_data()

    logger.info(
        "Live PM jobs: stored %d unique jobs from %d sources (keyword='%s', days_old=%d)",
        len(all_jobs),
        len(source_counts),
        keyword,
        days_old,
    )
    return all_jobs


# ─── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/listings", response_model=LiveSearchResponse)
async def get_live_listings():
    """Get the latest cached live Product Manager job listings."""
    data = _get_live_jobs_data()
    jobs = data.get(LIVE_JOBS_KEY, [])
    last_refresh = data.get(LAST_REFRESH_KEY)
    sources = data.get(SOURCES_KEY, {})

    # Check if cache is stale
    is_stale = False
    if last_refresh:
        try:
            refreshed = datetime.fromisoformat(last_refresh)
            age = datetime.now(UTC) - refreshed
            is_stale = age > timedelta(hours=CACHE_TTL_HOURS)
        except (ValueError, TypeError):
            is_stale = True

    return LiveSearchResponse(
        jobs=[LiveJobItem(**j) for j in jobs],
        total=len(jobs),
        sources=sources,
        searched_at=last_refresh or "",
        is_cached=not is_stale,
    )


@router.post("/refresh", response_model=LiveSearchResponse)
async def refresh_live_listings(
    keyword: str = Query("Product Manager", description="Job role to search for"),
    max_results: int = Query(50, ge=1, le=100, description="Max results to fetch per source"),
    days_old: int = Query(1, ge=0, le=7, description="Only include jobs posted within N days"),
):
    """Force-refresh live Product Manager job listings from all sources."""
    job_dicts = await search_and_store_live_pm_jobs(
        keyword=keyword,
        max_results=max_results,
        days_old=days_old,
    )

    data = _get_live_jobs_data()
    sources = data.get(SOURCES_KEY, {})

    return LiveSearchResponse(
        jobs=[LiveJobItem(**j) for j in job_dicts],
        total=len(job_dicts),
        sources=sources,
        searched_at=datetime.now(UTC).isoformat(),
        is_cached=False,
    )


@router.get("/last-refresh")
async def get_last_refresh():
    """Get the timestamp of the last refresh."""
    data = _get_live_jobs_data()
    last_refresh = data.get(LAST_REFRESH_KEY)
    sources = data.get(SOURCES_KEY, {})

    needs_refresh = True
    if last_refresh:
        try:
            refreshed = datetime.fromisoformat(last_refresh)
            age = datetime.now(UTC) - refreshed
            needs_refresh = age > timedelta(hours=CACHE_TTL_HOURS)
        except (ValueError, TypeError):
            pass

    return {
        "last_refresh": last_refresh,
        "needs_refresh": needs_refresh,
        "sources": sources,
        "cache_ttl_hours": CACHE_TTL_HOURS,
    }
