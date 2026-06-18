"""
Job Analyzer — orchestrates the full CV-to-application pipeline.

Pipeline:
  1. Parse CV → CandidateProfile
  2. Score all stored jobs via SemanticMatcher
  3. Filter to jobs that pass the threshold (default ≥60 %)
  4. Generate cover letter for each eligible job
  5. Launch BrowserAutomation to submit the application
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.models.profile import CandidateProfile, JobPosting, MatchResult, SeniorityLevel

logger = logging.getLogger(__name__)


# ─── Analysis result types ──────────────────────────────────────────────────


@dataclass
class AnalysisItem:
    """Result of analysing one job against the candidate profile."""

    job: JobPosting
    match: MatchResult
    eligible: bool = False
    cover_letter_path: Optional[str] = None
    apply_status: str = "skipped"  # skipped, submitted, captcha_blocked, error
    apply_error: Optional[str] = None


@dataclass
class AnalysisResult:
    """Full result of a pipeline run."""

    profile: CandidateProfile
    total_scored: int = 0
    eligible: int = 0
    applied: int = 0
    items: list[AnalysisItem] = field(default_factory=list)
    threshold: float = 0.60


# ─── Job Analyzer ───────────────────────────────────────────────────────────


class JobAnalyzer:
    """
    End-to-end pipeline that analyses a candidate's CV against available
    jobs and optionally applies to every eligible match.
    """

    def __init__(
        self,
        threshold: float | None = None,
        headless: bool = True,
        human_review: bool = True,
    ):
        self.threshold = threshold if threshold is not None else max(0.60, settings.match_threshold)
        self.headless = headless
        self.human_review = human_review
        self._matcher = None

    # ── Lazy imports ─────────────────────────────────────────────────────

    @property
    def matcher(self):
        if self._matcher is None:
            from backend.services.matcher import SemanticMatcher

            self._matcher = SemanticMatcher(threshold=self.threshold)
        return self._matcher

    @staticmethod
    def parse_cv(cv_path: str | Path) -> CandidateProfile:
        """Parse a CV file into a CandidateProfile."""
        from backend.services.cv_parser import CVParser

        parser = CVParser()
        return parser.parse(Path(cv_path))

    @staticmethod
    def load_jobs_from_storage() -> list[JobPosting]:
        """Load all stored jobs from JSON storage."""
        from backend.database import storage

        raw_jobs = storage.get_jobs()
        if not raw_jobs:
            return []
        return [JobPosting(**j) for j in raw_jobs]

    @staticmethod
    def jobs_from_orm(orm_jobs: list) -> list[JobPosting]:
        """Convert ORM job models to JobPosting objects (sync helper)."""
        jobs = []
        for j in orm_jobs:
            jobs.append(
                JobPosting(
                    id=j.id,
                    title=j.title,
                    company=j.company,
                    location=j.location,
                    description=j.description or "",
                    url=j.url,
                    source=j.source,
                    salary_range=j.salary_range,
                    remote=j.remote,
                    posted_date=j.posted_date,
                    skills_required=j.skills_required or [],
                    seniority=SeniorityLevel(j.seniority) if j.seniority else SeniorityLevel.UNKNOWN,
                )
            )
        return jobs

    @staticmethod
    async def load_jobs_async(db_session) -> list[JobPosting]:
        """
        Load jobs via async SQLAlchemy session (used by API endpoint).

        This is a separate async method so the API endpoint can await it.
        """
        from sqlalchemy import select

        from backend.models.db_models import JobModel

        result = await db_session.execute(
            select(JobModel).order_by(JobModel.created_at.desc()).limit(100)
        )
        orm_jobs = result.scalars().all()
        return JobAnalyzer.jobs_from_orm(orm_jobs)

    # ── Core analysis ────────────────────────────────────────────────────

    def analyze(
        self,
        profile: CandidateProfile,
        jobs: list[JobPosting] | None = None,
        top_k: int = 50,
    ) -> AnalysisResult:
        """
        Score all jobs against the profile and determine eligibility.

        Args:
            profile: Parsed candidate profile.
            jobs: Job postings to score. If None, loads from storage.
            top_k: Max number of top-scoring jobs to return.

        Returns:
            AnalysisResult with items sorted by score descending.
        """
        if jobs is None:
            jobs = self.load_jobs_from_storage()

        if not jobs:
            logger.warning("No jobs available to analyze")
            return AnalysisResult(profile=profile, threshold=self.threshold)

        # Score all jobs
        results = self.matcher.rank(profile, jobs, top_k=top_k)

        items: list[AnalysisItem] = []
        eligible_count = 0

        for r in results:
            # Use the analyzer's own threshold instead of the matcher's
            eligible = r.score >= self.threshold
            if eligible:
                eligible_count += 1
            items.append(
                AnalysisItem(
                    job=r.job,
                    match=r,
                    eligible=eligible,
                )
            )

        return AnalysisResult(
            profile=profile,
            total_scored=len(results),
            eligible=eligible_count,
            applied=0,
            items=items,
            threshold=self.threshold,
        )

    # ── Analysis + apply pipeline ────────────────────────────────────────

    def analyze_and_apply(
        self,
        profile: CandidateProfile,
        cv_path: str | Path = "",
        jobs: list[JobPosting] | None = None,
        cover_letter_dir: str | Path | None = None,
        max_applications: int = 10,
    ) -> AnalysisResult:
        """
        Full pipeline: analyze → generate cover letters → apply to eligible.

        Args:
            profile: Parsed candidate profile.
            cv_path: Path to CV file (for browser upload).
            jobs: Job postings to score. If None, loads from storage.
            cover_letter_dir: Where to save generated cover letters.
            max_applications: Cap on how many jobs to apply to.

        Returns:
            AnalysisResult with apply_status filled for eligible items.
        """
        result = self.analyze(profile, jobs)

        if not result.eligible:
            logger.info("No eligible jobs found (threshold = %.0f%%)", self.threshold * 100)
            return result

        # Cap the number of applications
        eligible_items = [it for it in result.items if it.eligible][:max_applications]

        # Generate cover letters for eligible jobs
        from backend.services.cover_letter_generator import CoverLetterGenerator

        cl_generator = CoverLetterGenerator()
        cl_dir = Path(cover_letter_dir) if cover_letter_dir else settings.cover_letter_dir
        cl_dir.mkdir(parents=True, exist_ok=True)

        for item in eligible_items:
            try:
                letter_path = cl_generator.generate_and_save(
                    profile=profile,
                    job=item.job,
                    match=item.match,
                    tone="professional",
                    output_dir=cl_dir,
                )
                item.cover_letter_path = str(letter_path)
                logger.info(
                    "Cover letter generated for %s @ %s: %s",
                    item.job.title,
                    item.job.company,
                    letter_path,
                )
            except Exception as e:
                logger.warning("Cover letter generation failed for %s: %s", item.job.title, e)
                item.cover_letter_path = None

        # Apply to each eligible job via browser automation.
        # A new BrowserAutomation is created per job so we can pass the
        # correct cover letter path for each application.
        applied = 0
        from backend.services.browser_automation import BrowserAutomation

        for item in eligible_items:
            if not item.job.url:
                logger.info("No URL for %s @ %s — skipping", item.job.title, item.job.company)
                continue

            logger.info(
                "Applying to %s @ %s (score: %.0f%%)…",
                item.job.title,
                item.job.company,
                item.match.score * 100,
            )

            automator = BrowserAutomation(
                profile=profile,
                cv_path=str(cv_path) if cv_path else "",
                cover_letter_path=item.cover_letter_path or "",
                headless=self.headless,
                human_review=self.human_review,
            )

            try:
                automator.launch()
                apply_result = automator.apply(url=item.job.url, use_ats_adapter=True)
                item.apply_status = apply_result.status
                item.apply_error = apply_result.error_message

                if apply_result.status == "submitted":
                    applied += 1
                    logger.info("✅ Submitted application to %s", item.job.title)

                if apply_result.status == "captcha_blocked" and not self.human_review:
                    logger.warning("CAPTCHA blocked — stopping pipeline")
                    automator.close()
                    break

            except Exception as e:
                item.apply_status = "error"
                item.apply_error = str(e)
                logger.error("Apply failed for %s: %s", item.job.title, e)

                if not self.human_review:
                    automator.close()
                    break
            finally:
                automator.close()

        result.applied = applied
        return result


# ─── Convenience function ───────────────────────────────────────────────────


def quick_analyze(
    cv_path: str | Path,
    threshold: float = 0.60,
    auto_apply: bool = False,
    headless: bool = True,
    human_review: bool = True,
    max_apps: int = 10,
) -> AnalysisResult:
    """
    One-shot convenience: parse a CV, analyze against stored jobs, optionally apply.

    Args:
        cv_path: Path to the CV file.
        threshold: Minimum match score (0.0–1.0).
        auto_apply: If True, also apply to eligible jobs.
        headless: Run browser in headless mode.
        human_review: Pause for human review before submitting.
        max_apps: Max jobs to apply to.

    Returns:
        AnalysisResult with all scores and (if auto_apply) apply results.
    """
    analyzer = JobAnalyzer(
        threshold=threshold,
        headless=headless,
        human_review=human_review,
    )

    profile = analyzer.parse_cv(cv_path)

    if auto_apply:
        return analyzer.analyze_and_apply(
            profile=profile,
            cv_path=cv_path,
            max_applications=max_apps,
        )

    return analyzer.analyze(profile)
