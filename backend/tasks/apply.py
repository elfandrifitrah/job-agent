"""
Celery task — background browser-automated job application.
Uses synchronous SQLAlchemy to avoid asyncio.run() issues in Celery workers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session as SASession

from backend.celery_app import celery_app
from backend.models.db_models import ApplicationModel, JobModel, ProfileModel
from backend.models.profile import CandidateProfile, Education, Experience, SeniorityLevel, Skill
from backend.tasks.db import get_sync_engine

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="apply_to_job", max_retries=1, time_limit=300)
def apply_to_job(
    self,
    application_id: str,
    headless: bool = True,
):
    """Execute a browser-automated application in the background."""
    logger.info("Task apply_to_job: application_id='%s'", application_id)

    engine = get_sync_engine()
    try:
        with SASession(engine) as db:
            # Load application
            app = db.execute(
                select(ApplicationModel).where(ApplicationModel.id == application_id)
            ).scalar_one_or_none()

            if not app:
                return {"status": "error", "message": "Application not found"}

            # Update status
            app.status = "applying"
            db.commit()

            # Load profile and job
            orm_profile = db.execute(
                select(ProfileModel).where(ProfileModel.id == app.profile_id)
            ).scalar_one_or_none()

            orm_job = db.execute(
                select(JobModel).where(JobModel.id == app.job_id)
            ).scalar_one_or_none()

            if not orm_profile or not orm_job or not orm_job.url:
                app.status = "error"
                app.error_log = "Missing profile, job, or URL"
                db.commit()
                return {"status": "error", "message": app.error_log}

            # Reconstruct profile
            profile = CandidateProfile(
                full_name=orm_profile.full_name,
                email=orm_profile.email,
                phone=orm_profile.phone,
                location=orm_profile.location,
                linkedin_url=orm_profile.linkedin_url,
                github_url=orm_profile.github_url,
                portfolio_url=orm_profile.portfolio_url,
                raw_text=orm_profile.raw_text or "",
                skills=[Skill(**s) for s in (orm_profile.skills or [])],
                experiences=[Experience(**e) for e in (orm_profile.experiences or [])],
                education=[Education(**e) for e in (orm_profile.education or [])],
                years_of_experience=orm_profile.years_of_experience,
                seniority=SeniorityLevel(orm_profile.seniority),
                remote_preferred=orm_profile.remote_preferred,
            )

            # Launch automation
            from backend.services.browser_automation import BrowserAutomation

            automator = BrowserAutomation(
                profile=profile,
                cv_path="",
                headless=headless,
                human_review=False,
            )

            try:
                automator.launch()
                result = automator.apply(url=orm_job.url, use_ats_adapter=True)

                app.status = result.status
                app.ats_name = result.ats
                app.fields_filled = result.fields_filled
                app.total_fields = result.total_fields
                app.screenshot_path = result.screenshot_path
                if result.status == "submitted":
                    app.submitted_at = datetime.now(UTC)
                if result.error_message:
                    app.error_log = result.error_message[:1000]

                db.commit()
                return {
                    "status": result.status,
                    "ats": result.ats,
                    "fields_filled": result.fields_filled,
                }
            except Exception as e:
                app.status = "error"
                app.error_log = str(e)[:1000]
                db.commit()
                raise
            finally:
                automator.close()
    except Exception as e:
        logger.error("Apply task failed: %s", e)
        raise self.retry(exc=e, countdown=60)
