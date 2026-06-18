"""
Celery app configuration for background job processing.

Tasks:
  - discover_jobs: background job discovery
  - match_profile: semantic matching (CPU-heavy)
  - apply_to_job: browser automation (long-running)
  - generate_cover_letter: LLM API call
"""

from __future__ import annotations

import logging

from celery import Celery

from backend.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "job_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["backend.tasks.discovery", "backend.tasks.matching", "backend.tasks.apply"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,          # 10 minutes max per task
    task_soft_time_limit=540,     # 9 minutes soft limit
    worker_max_tasks_per_child=10,  # Restart worker after 10 tasks (memory leak prevention)
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)


@celery_app.task(bind=True, name="health_check")
def health_check(self):
    """Simple health check task."""
    return {"status": "ok", "task_id": self.request.id}
