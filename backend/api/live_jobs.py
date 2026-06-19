"""
API router for live Product Manager job listings.
Multi-source: fetches from Jobicy (free, no key) + Adzuna (free tier, needs API key).
Stores results, deduplicates, and tracks source breakdown.
Runs on-demand via API or daily via APScheduler.

Falls back to sample seed data when no real jobs are available.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import storage as json_storage
from backend.storage.backend import StorageBackend
from backend.storage.deps import get_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live-jobs", tags=["live-jobs"])

SAMPLE_PM_JOBS = [
    {"id":"sample_001","title":"Senior Product Manager","company":"Google","location":"Mountain View, CA (Remote)","description":"Drive product strategy for Google Cloud Platform. Define roadmap, gather requirements, and work with engineering to deliver features that serve millions of users worldwide.","url":"https://careers.google.com/jobs/results/","source":"sample","salary_range":"$180K-$250K","remote":True,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"senior","skills_required":["Product Management","Cloud Computing","Agile","Data Analysis","Stakeholder Management","A/B Testing","Strategy"]},
    {"id":"sample_002","title":"Product Manager — Payments","company":"Stripe","location":"San Francisco, CA (Remote)","description":"Own the payments platform product roadmap. Work with merchants and financial partners to build the next generation of online payment infrastructure.","url":"https://stripe.com/jobs","source":"sample","salary_range":"$170K-$230K","remote":True,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"senior","skills_required":["Product Management","Payments","Fintech","API Design","User Research","SQL"]},
    {"id":"sample_003","title":"Product Manager","company":"Microsoft","location":"Redmond, WA (Remote)","description":"Lead product development for Microsoft Teams. Define features, prioritize backlog, analyze usage data, and ship experiences that empower hybrid work.","url":"https://careers.microsoft.com/","source":"sample","salary_range":"$150K-$210K","remote":True,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"senior","skills_required":["Product Management","SaaS","User Analytics","Agile","Communication","Roadmapping"]},
    {"id":"sample_004","title":"Associate Product Manager","company":"Airbnb","location":"San Francisco, CA (Hybrid)","description":"Join Airbnb's APM program. Rotate across teams working on search, payments, trust & safety, and host tools. 2-year rotational program with mentorship.","url":"https://careers.airbnb.com/","source":"sample","salary_range":"$120K-$150K","remote":False,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"mid","skills_required":["Product Management","User Research","Data Analysis","Prototyping","Cross-functional Collaboration"]},
    {"id":"sample_005","title":"Senior Product Manager — AI/ML","company":"Anthropic","location":"San Francisco, CA","description":"Define product direction for Claude AI platform. Work alongside ML researchers to translate cutting-edge AI capabilities into intuitive product experiences.","url":"https://www.anthropic.com/careers","source":"sample","salary_range":"$200K-$300K","remote":True,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"senior","skills_required":["Product Management","Machine Learning","AI","API Design","Technical Communication","Strategy"]},
    {"id":"sample_006","title":"Product Manager — Developer Platform","company":"Vercel","location":"Remote (Global)","description":"Own the developer experience for Vercel's deployment platform. Define product specs, work with open-source communities, and ship features that make web development faster.","url":"https://vercel.com/careers","source":"sample","salary_range":"$160K-$220K","remote":True,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"senior","skills_required":["Product Management","Developer Tools","Web Technologies","API Design","DX","Analytics"]},
    {"id":"sample_007","title":"Product Manager — Growth","company":"Notion","location":"New York, NY (Hybrid)","description":"Drive user acquisition, activation, and retention for Notion. Run experiments, analyze funnels, and build features that turn casual users into power users.","url":"https://www.notion.so/careers","source":"sample","salary_range":"$155K-$215K","remote":False,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"mid","skills_required":["Product Management","Growth","Experimentation","Data Analysis","SQL","User Psychology"]},
    {"id":"sample_008","title":"Director of Product — Fintech","company":"Revolut","location":"London, UK (Remote)","description":"Lead the fintech product team. Define the long-term product vision for Revolut's banking and investment products across European and Asian markets.","url":"https://www.revolut.com/careers","source":"sample","salary_range":"$190K-$280K","remote":True,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"executive","skills_required":["Product Leadership","Fintech","Strategy","Team Management","Regulatory Knowledge","P&L Management"]},
    {"id":"sample_009","title":"Product Manager — Marketplace","company":"DoorDash","location":"San Francisco, CA","description":"Own the Dasher experience product area. Build tools that help delivery partners earn more, work flexibly, and feel supported.","url":"https://careers.doordash.com/","source":"sample","salary_range":"$145K-$200K","remote":True,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"mid","skills_required":["Product Management","Marketplace","Logistics","Data Analysis","User Research","Experimentation"]},
    {"id":"sample_010","title":"Principal Product Manager — Infrastructure","company":"Netflix","location":"Los Gatos, CA","description":"Define the strategy for Netflix's cloud infrastructure platform. Drive efficiency, reliability, and developer velocity for one of the world's largest streaming services.","url":"https://jobs.netflix.com/","source":"sample","salary_range":"$250K-$400K","remote":False,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"principal","skills_required":["Product Management","Cloud Infrastructure","Distributed Systems","Strategy","Technical Leadership","Cost Optimization"]},
    {"id":"sample_011","title":"Product Manager","company":"Spotify","location":"New York, NY (Hybrid)","description":"Shape the future of music discovery on Spotify. Build personalized recommendation features that connect artists with listeners at global scale.","url":"https://www.lifeatspotify.com/jobs","source":"sample","salary_range":"$140K-$195K","remote":True,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"mid","skills_required":["Product Management","Recommendation Systems","A/B Testing","Data Analysis","User Research","Personalization"]},
    {"id":"sample_012","title":"Senior Product Manager — API Platform","company":"Twilio","location":"San Francisco, CA (Remote)","description":"Own Twilio's communications API platform product. Define developer experience improvements, API standards, and partner integrations.","url":"https://www.twilio.com/company/jobs","source":"sample","salary_range":"$165K-$225K","remote":True,"posted_date":(datetime.now(UTC)-timedelta(hours=random.randint(1,48))).isoformat(),"seniority":"senior","skills_required":["Product Management","API Platform","Developer Experience","Technical Product","SaaS","Integration Design"]},
]


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


def _get_or_create_live_jobs_data() -> dict[str, Any]:
    """Get the live jobs section from the data store, initialising if absent."""
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

async def _search_source(
    source_cls: type,
    params: Any,
) -> tuple[list[dict[str, Any]], int]:
    """Run a single source search in a thread pool and return (job_dicts, count)."""
    source = source_cls()
    loop = asyncio.get_running_loop()
    job_postings = await loop.run_in_executor(None, source.search, params)
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
    jobicy_jobs, jobicy_count = await _search_source(JobicySource, params)
    for j in jobicy_jobs:
        jid = j.get("id", "")
        if jid and jid not in seen_ids:
            seen_ids.add(jid)
            all_jobs.append(j)
    source_counts["jobicy"] = len(jobicy_jobs)
    logger.info("Jobicy: %d jobs", jobicy_count)

    # --- Source 2: Adzuna (only if API keys are configured) ---
    if settings.adzuna_app_id and settings.adzuna_api_key:
        adzuna_jobs, adzuna_count = await _search_source(AdzunaSource, params)
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
    firecrawl_jobs, firecrawl_count = await _search_source(FirecrawlSource, params)
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

    # --- Fallback: seed sample jobs if no real jobs found ---
    if not all_jobs:
        logger.info("No real jobs found — falling back to sample data")
        all_jobs = [j.copy() for j in SAMPLE_PM_JOBS]
        for j in all_jobs:
            j["source"] = "sample"
        source_counts = {"sample": len(all_jobs)}

    # --- Store merged results ---
    data = _get_or_create_live_jobs_data()
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
    """Get the latest cached live Product Manager job listings.

    Returns sample data as fallback when no real jobs are available.
    """
    data = _get_or_create_live_jobs_data()
    jobs = data.get(LIVE_JOBS_KEY, [])
    last_refresh = data.get(LAST_REFRESH_KEY)
    sources = data.get(SOURCES_KEY, {})

    # Fallback to sample data if cache is empty
    if not jobs:
        jobs = [j.copy() for j in SAMPLE_PM_JOBS]
        sources = {"sample": len(jobs)}
        last_refresh = None

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


@router.post("/seed", response_model=LiveSearchResponse)
async def seed_sample_listings():
    """Seed the live jobs cache with sample Product Manager listings.

    Useful for testing the dashboard when real job sources are unavailable.
    """
    sample = [j.copy() for j in SAMPLE_PM_JOBS]
    data = _get_or_create_live_jobs_data()
    data[LIVE_JOBS_KEY] = sample
    data[LAST_REFRESH_KEY] = datetime.now(UTC).isoformat()
    data[SOURCES_KEY] = {"sample": len(sample)}
    _save_live_jobs_data()
    logger.info("Seeded %d sample live jobs", len(sample))
    return LiveSearchResponse(
        jobs=[LiveJobItem(**j) for j in sample],
        total=len(sample),
        sources={"sample": len(sample)},
        searched_at=datetime.now(UTC).isoformat(),
        is_cached=False,
    )


async def seed_sample_listings_if_empty() -> int:
    """Seed sample data only if the live jobs cache is currently empty.

    Returns the number of jobs seeded (0 if already populated).
    Used at application startup to ensure the dashboard never starts blank.
    """
    data = _get_or_create_live_jobs_data()
    existing = data.get(LIVE_JOBS_KEY, [])
    if existing:
        return 0

    sample = [j.copy() for j in SAMPLE_PM_JOBS]
    data[LIVE_JOBS_KEY] = sample
    data[LAST_REFRESH_KEY] = datetime.now(UTC).isoformat()
    data[SOURCES_KEY] = {"sample": len(sample)}
    _save_live_jobs_data()
    logger.info("Auto-seeded %d sample live jobs (cache was empty)", len(sample))
    return len(sample)


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

    data = _get_or_create_live_jobs_data()
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
    data = _get_or_create_live_jobs_data()
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
