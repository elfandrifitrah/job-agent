"""
APScheduler-based daily refresh for live Product Manager job listings.

Runs daily to fetch the latest remote Product Manager jobs from Jobicy
and stores them so the dashboard always has fresh listings.
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None


async def _refresh_pm_jobs() -> None:
    """Background task: fetch and store latest Product Manager remote jobs."""
    from backend.api.live_jobs import search_and_store_live_pm_jobs

    logger.info("[Scheduler] Starting live PM jobs refresh...")
    try:
        jobs = await search_and_store_live_pm_jobs(
            keyword="Product Manager",
            max_results=50,
            days_old=3,
        )
        logger.info("[Scheduler] Refreshed %d live PM jobs", len(jobs))
    except Exception as e:
        logger.error("[Scheduler] Failed to refresh live PM jobs: %s", e)


async def _scan_career_pages() -> None:
    """Background task: scan company career pages for new PM job listings."""
    from backend.services.career_page_scanner import scan_all_career_pages

    logger.info("[Scheduler] Starting career page scan...")
    try:
        jobs = await scan_all_career_pages(
            role_keyword="Product Manager",
            max_companies=15,
        )
        if jobs:
            from backend.database import storage
            data = storage._data
            key = "live_jobs"
            existing = data.get(key, [])
            seen_ids = {j.get("id", "") for j in existing}
            added = 0
            for j in jobs:
                jid = j.get("id", "")
                if jid and jid not in seen_ids:
                    seen_ids.add(jid)
                    existing.append(j)
                    added += 1
            # Prune jobs older than 30 days by removing entries with no recent posted_date
            data[key] = existing
            storage._save()
            logger.info("[Scheduler] Career pages: %d new jobs added (total live: %d)", added, len(existing))
        else:
            logger.info("[Scheduler] Career pages: no new jobs found")
    except Exception as e:
        logger.error("[Scheduler] Failed to scan career pages: %s", e)


async def _send_daily_digest() -> None:
    """Background task: send daily email digest if notifications are enabled."""
    from backend.tasks.email_digest import send_daily_digest

    logger.info("[Scheduler] Starting daily email digest...")
    try:
        success = await send_daily_digest()
        logger.info("[Scheduler] Daily digest %s", "sent" if success else "skipped")
    except Exception as e:
        logger.error("[Scheduler] Failed to send daily digest: %s", e)


def start_scheduler() -> AsyncIOScheduler:
    """Start the APScheduler that refreshes live job listings continuously.

    Call this once on application startup.
    Returns the scheduler instance.
    """
    global scheduler

    if scheduler and scheduler.running:
        logger.info("[Scheduler] Already running")
        return scheduler

    scheduler = AsyncIOScheduler()

    # Run every 6 hours (more frequent = fresher jobs)
    scheduler.add_job(
        _refresh_pm_jobs,
        trigger=IntervalTrigger(hours=6),
        id="refresh_live_pm_jobs",
        name="Refresh live Product Manager jobs",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Run career page scan every 12 hours
    scheduler.add_job(
        _scan_career_pages,
        trigger=IntervalTrigger(hours=12),
        id="scan_career_pages",
        name="Scan company career pages",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Also run once immediately on startup to populate initial data
    scheduler.add_job(
        _refresh_pm_jobs,
        trigger="date",
        id="refresh_live_pm_jobs_initial",
        name="Initial refresh of live PM jobs",
        misfire_grace_time=300,
    )

    # Initial career page scan shortly after startup
    scheduler.add_job(
        _scan_career_pages,
        trigger="date",
        id="scan_career_pages_initial",
        name="Initial career page scan",
        misfire_grace_time=300,
    )

    # Schedule daily email digest (runs at 08:00 UTC)
    scheduler.add_job(
        _send_daily_digest,
        trigger="cron",
        hour=8,
        minute=0,
        id="send_daily_digest",
        name="Send daily PM job digest email",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("[Scheduler] Started — jobs refresh every 6h, career pages every 12h")
    return scheduler


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler on app shutdown."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped")
