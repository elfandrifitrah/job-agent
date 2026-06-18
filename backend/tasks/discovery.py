"""
Celery task — background job discovery from multiple sources.
"""

from __future__ import annotations

import logging

from backend.celery_app import celery_app
from backend.services.job_discovery import JobDiscovery, SearchParams

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="discover_jobs", max_retries=2)
def discover_jobs(
    self,
    role: str = "Software Engineer",
    location: str = "",
    remote: bool = False,
    limit: int = 20,
    days_old: int = 14,
):
    """Discover jobs from all configured sources."""
    logger.info("Task discover_jobs: role='%s', location='%s'", role, location)

    params = SearchParams(
        role=role,
        location=location,
        remote=remote,
        max_results=limit,
        days_old=days_old,
    )

    try:
        discovery = JobDiscovery()
        result = discovery.search(params)

        return {
            "status": "completed",
            "total_jobs": len(result.jobs),
            "sources": result.source_counts,
            "errors": result.errors,
        }
    except Exception as e:
        logger.error("Job discovery failed: %s", e)
        raise self.retry(exc=e, countdown=60)
