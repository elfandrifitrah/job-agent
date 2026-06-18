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

    logger.info("[Scheduler] Starting daily live PM jobs refresh...")
    try:
        jobs = await search_and_store_live_pm_jobs(
            keyword="Product Manager",
            max_results=50,
            days_old=1,
        )
        logger.info("[Scheduler] Refreshed %d live PM jobs", len(jobs))
    except Exception as e:
        logger.error("[Scheduler] Failed to refresh live PM jobs: %s", e)


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
    """Start the APScheduler that refreshes live job listings daily.

    Call this once on application startup.
    Returns the scheduler instance.
    """
    global scheduler

    if scheduler and scheduler.running:
        logger.info("[Scheduler] Already running")
        return scheduler

    scheduler = AsyncIOScheduler()

    # Run every 24 hours
    scheduler.add_job(
        _refresh_pm_jobs,
        trigger=IntervalTrigger(hours=24),
        id="refresh_live_pm_jobs",
        name="Refresh live Product Manager jobs",
        replace_existing=True,
        misfire_grace_time=3600,  # 1 hour grace
    )

    # Also run once immediately on startup to populate initial data
    scheduler.add_job(
        _refresh_pm_jobs,
        trigger="date",  # Run once now
        id="refresh_live_pm_jobs_initial",
        name="Initial refresh of live PM jobs",
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
    logger.info("[Scheduler] Started — daily PM jobs refresh scheduled")
    return scheduler


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler on app shutdown."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped")
