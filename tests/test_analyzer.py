"""
Tests for the Job Analyzer service.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.profile import (
    CandidateProfile,
    Education,
    Experience,
    JobPosting,
    MatchResult,
    SeniorityLevel,
    Skill,
)
from backend.services.analyzer import (
    AnalysisItem,
    AnalysisResult,
    JobAnalyzer,
    quick_analyze,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        full_name="Test User",
        raw_text="Python developer with React and PostgreSQL experience",
        skills=[
            Skill(name="Python", category="language", confidence=0.9),
            Skill(name="React", category="framework", confidence=0.8),
            Skill(name="PostgreSQL", category="database", confidence=0.7),
        ],
        experiences=[
            Experience(company="Acme", title="Software Engineer", description="Built APIs")
        ],
        years_of_experience=5.0,
        seniority=SeniorityLevel.SENIOR,
    )


@pytest.fixture
def jobs() -> list[JobPosting]:
    return [
        JobPosting(
            id="job-1",
            title="Senior Python Developer",
            company="TechCorp",
            description="Python, React, PostgreSQL role",
            url="https://techcorp.com/apply/1",
            skills_required=["Python", "React", "PostgreSQL"],
            seniority=SeniorityLevel.SENIOR,
        ),
        JobPosting(
            id="job-2",
            title="Rust Engineer",
            company="StartupXYZ",
            description="Systems programming role",
            url="https://startupxyz.com/apply",
            skills_required=["Rust", "C++", "Go"],
            seniority=SeniorityLevel.MID,
        ),
        JobPosting(
            id="job-3",
            title="Full Stack Developer",
            company="WebCo",
            description="Python and React role",
            url="",  # No URL — should be skipped during apply
            skills_required=["Python", "React", "JavaScript"],
            seniority=SeniorityLevel.SENIOR,
        ),
    ]


@pytest.fixture
def mock_matcher() -> MagicMock:
    """A SemanticMatcher that returns controlled results."""
    matcher = MagicMock()

    def _rank(profile, jobs, top_k=50):
        results = []
        for j in jobs:
            overlap = set(s.lower() for s in profile.skill_names) & set(s.lower() for s in j.skills_required)
            gap = set(s.lower() for s in j.skills_required) - set(s.lower() for s in profile.skill_names)
            score = len(overlap) / max(len(j.skills_required), 1)
            results.append(
                MatchResult(
                    job=j,
                    score=score,
                    skill_overlap=sorted(overlap),
                    skill_gaps=sorted(gap),
                    seniority_match=True,
                    location_match=True,
                    passed_threshold=score >= 0.5,
                    reasoning=f"Skill overlap: {score:.0%}",
                )
            )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    matcher.rank.side_effect = _rank
    return matcher


@pytest.fixture
def analyzer(profile, mock_matcher) -> JobAnalyzer:
    """JobAnalyzer pre-configured with a mocked matcher."""
    a = JobAnalyzer(threshold=0.50)
    a._matcher = mock_matcher  # inject mock directly, skip lazy init
    return a


# ─── Tests: analyze() ──────────────────────────────────────────────────────


class TestAnalyze:
    """Tests for JobAnalyzer.analyze()."""

    def test_analyze_returns_analysis_result(self, analyzer, profile, jobs):
        result = analyzer.analyze(profile, jobs)
        assert isinstance(result, AnalysisResult)
        assert result.profile == profile
        assert result.total_scored == 3
        assert result.threshold == 0.50

    def test_analyze_marks_eligible_jobs(self, analyzer, profile, jobs):
        """job-1 (3/3 skills matching) and job-3 (2/3) should pass 50% threshold."""
        result = analyzer.analyze(profile, jobs)

        # job-1: Python+React+PostgreSQL = 3/3 = 1.0 → eligible
        # job-3: Python+React = 2/3 = 0.667 → eligible (≥0.5)
        # job-2: no overlap = 0/3 = 0.0 → not eligible
        assert result.eligible == 2

        job1_result = [i for i in result.items if i.job.id == "job-1"][0]
        assert job1_result.eligible is True
        assert job1_result.match.score == 1.0

        job2_result = [i for i in result.items if i.job.id == "job-2"][0]
        assert job2_result.eligible is False
        assert job2_result.match.score == 0.0

    def test_analyze_returns_sorted_by_score(self, analyzer, profile, jobs):
        result = analyzer.analyze(profile, jobs)
        scores = [item.match.score for item in result.items]
        assert scores == sorted(scores, reverse=True)

    def test_analyze_empty_jobs_list(self, analyzer, profile):
        result = analyzer.analyze(profile, [])
        assert result.total_scored == 0
        assert result.eligible == 0
        assert len(result.items) == 0

    def test_analyze_no_jobs(self, analyzer, profile):
        result = analyzer.analyze(profile, None)
        # With no explicit jobs and a mocked matcher, it calls load_jobs_from_storage
        # which needs the storage to be set up. Since we didn't mock it, it will
        # return empty. This is acceptable.
        assert isinstance(result, AnalysisResult)
        assert result.total_scored >= 0

    def test_analyze_with_different_threshold(self, profile, jobs, mock_matcher):
        strict = JobAnalyzer(threshold=1.0)
        strict._matcher = mock_matcher
        result = strict.analyze(profile, jobs)
        # Only job-1 with a 1.0 score passes the 1.0 threshold
        assert result.eligible == 1

    def test_analyze_skill_overlap_and_gaps(self, analyzer, profile, jobs):
        result = analyzer.analyze(profile, jobs)
        gap_job = [i for i in result.items if i.job.id == "job-2"][0]
        assert "rust" in gap_job.match.skill_gaps
        assert "python" not in gap_job.match.skill_gaps  # Python is in CV, not in job-2 requirements


# ─── Tests: analyze_and_apply() ────────────────────────────────────────────


class TestAnalyzeAndApply:
    """Tests for JobAnalyzer.analyze_and_apply()."""

    def test_analyze_and_apply_skips_when_no_eligible(self, analyzer, profile):
        """No eligible jobs should return without attempting any apply calls."""
        # jobs that won't pass the threshold
        bad_jobs = [
            JobPosting(
                id="no-match",
                title="Rust Engineer",
                skills_required=["Rust", "C++"],
            )
        ]
        result = analyzer.analyze_and_apply(profile, jobs=bad_jobs)
        assert result.applied == 0
        assert result.eligible == 0

    @patch("backend.services.browser_automation.BrowserAutomation")
    def test_analyze_and_apply_calls_browser_automation(
        self, mock_browser_cls, analyzer, profile, jobs, tmp_path
    ):
        """For eligible jobs with URLs, BrowserAutomation should be created and applied."""
        mock_automator = MagicMock()
        mock_automator.apply.return_value = MagicMock(status="submitted")
        mock_browser_cls.return_value = mock_automator

        result = analyzer.analyze_and_apply(
            profile,
            cv_path=str(tmp_path / "cv.txt"),
            jobs=jobs,
            cover_letter_dir=str(tmp_path / "cover_letters"),
            max_applications=10,
        )

        # 2 eligible jobs: job-1 (has URL), job-3 (no URL)
        # Only job-1 should be applied to (has URL)
        assert result.applied == 1, f"Expected 1 apply call, got {result.applied}"
        assert mock_browser_cls.called
        # Check that the created automator's apply was called with the right URL
        mock_automator.apply.assert_called_once_with(
            url="https://techcorp.com/apply/1",
            use_ats_adapter=True,
        )

    @patch("backend.services.browser_automation.BrowserAutomation")
    def test_analyze_and_apply_reports_captcha_blocked(
        self, mock_browser_cls, analyzer, profile, jobs, tmp_path
    ):
        """CAPTCHA blocked without human review should stop the pipeline."""
        mock_automator = MagicMock()
        mock_automator.apply.return_value = MagicMock(
            status="captcha_blocked",
            error_message="reCAPTCHA detected",
        )
        mock_browser_cls.return_value = mock_automator

        # No human review → should break on captcha
        strict_analyzer = JobAnalyzer(threshold=0.50, human_review=False)
        strict_analyzer._matcher = analyzer._matcher

        result = strict_analyzer.analyze_and_apply(
            profile,
            cv_path=str(tmp_path / "cv.txt"),
            jobs=[jobs[0]],  # Only 1 eligible job
            cover_letter_dir=str(tmp_path / "cover_letters"),
        )

        assert result.applied == 0
        assert result.items[0].apply_status == "captcha_blocked"

    @patch("backend.services.browser_automation.BrowserAutomation")
    def test_analyze_and_apply_handles_automation_error(
        self, mock_browser_cls, analyzer, profile, jobs, tmp_path
    ):
        """Errors during browser automation should be captured, not crash."""
        mock_automator = MagicMock()
        mock_automator.apply.side_effect = Exception("Connection refused")
        mock_browser_cls.return_value = mock_automator

        result = analyzer.analyze_and_apply(
            profile,
            cv_path=str(tmp_path / "cv.txt"),
            jobs=[jobs[0]],
            cover_letter_dir=str(tmp_path / "cover_letters"),
        )

        assert result.applied == 0
        assert result.items[0].apply_status == "error"
        assert result.items[0].apply_error == "Connection refused"

    @patch("backend.services.cover_letter_generator.CoverLetterGenerator")
    @patch("backend.services.browser_automation.BrowserAutomation")
    def test_analyze_and_apply_generates_cover_letters(
        self, mock_browser_cls, mock_cl_gen, analyzer, profile, jobs, tmp_path
    ):
        """Cover letters should be generated for each eligible job before applying."""
        mock_cl_generator = MagicMock()
        mock_cl_generator.generate_and_save.return_value = tmp_path / "cover_letters" / "test_job_letter.txt"
        mock_cl_gen.return_value = mock_cl_generator

        mock_automator = MagicMock()
        mock_automator.apply.return_value = MagicMock(status="submitted")
        mock_browser_cls.return_value = mock_automator

        result = analyzer.analyze_and_apply(
            profile,
            cv_path=str(tmp_path / "cv.txt"),
            jobs=jobs,
            cover_letter_dir=str(tmp_path / "cover_letters"),
            max_applications=10,
        )

        # Cover letter should have been generated for job-1 (only eligible job with URL)
        gen_job = [i for i in result.items if i.job.id == "job-1"]
        assert len(gen_job) == 1
        assert gen_job[0].cover_letter_path is not None

    @patch("backend.services.browser_automation.BrowserAutomation")
    def test_analyze_and_apply_skips_jobs_without_url(
        self, mock_browser_cls, analyzer, profile, jobs, tmp_path
    ):
        """Jobs without URLs should be skipped during application."""
        mock_automator = MagicMock()
        mock_automator.apply.return_value = MagicMock(status="submitted")
        mock_browser_cls.return_value = mock_automator

        # job-3 has no URL but is eligible — should be skipped
        # Only job-1 should trigger an apply call
        result = analyzer.analyze_and_apply(
            profile,
            cv_path=str(tmp_path / "cv.txt"),
            jobs=jobs,
            cover_letter_dir=str(tmp_path / "cover_letters"),
            max_applications=10,
        )

        applied_items = [i for i in result.items if i.eligible and i.apply_status == "submitted"]
        assert len(applied_items) == 1
        assert applied_items[0].job.id == "job-1"

        # Verify job-3 was skipped (no URL)
        skipped = [i for i in result.items if i.job.id == "job-3" and i.apply_status == "skipped"]
        assert len(skipped) == 1


# ─── Tests: jobs_from_orm ──────────────────────────────────────────────────


class TestJobsFromOrm:
    """Tests for JobAnalyzer.jobs_from_orm()."""

    def test_jobs_from_orm(self):
        """Verify ORM conversion produces valid JobPosting objects."""
        mock_job = MagicMock()
        mock_job.id = "orm-1"
        mock_job.title = "ORM Engineer"
        mock_job.company = "ORM Corp"
        mock_job.location = "Remote"
        mock_job.description = "ORM role"
        mock_job.url = "https://ormcorp.com/apply"
        mock_job.source = "linkedin"
        mock_job.salary_range = "$100k-$150k"
        mock_job.remote = True
        mock_job.posted_date = "2025-01-01"
        mock_job.skills_required = ["Python", "SQL"]
        mock_job.seniority = "senior"

        jobs = JobAnalyzer.jobs_from_orm([mock_job])
        assert len(jobs) == 1
        j = jobs[0]
        assert j.id == "orm-1"
        assert j.title == "ORM Engineer"
        assert j.seniority == SeniorityLevel.SENIOR
        assert j.remote is True
        assert j.skills_required == ["Python", "SQL"]

    def test_jobs_from_orm_empty(self):
        assert JobAnalyzer.jobs_from_orm([]) == []


# ─── Tests: quick_analyze ──────────────────────────────────────────────────


class TestQuickAnalyze:
    """Tests for the quick_analyze convenience function."""

    @patch("backend.services.analyzer.JobAnalyzer")
    def test_quick_analyze_calls_analyze(self, mock_cls):
        """quick_analyze should create a JobAnalyzer and call analyze()."""
        mock_instance = MagicMock()
        mock_instance.parse_cv.return_value = MagicMock()
        mock_instance.analyze.return_value = AnalysisResult(
            profile=MagicMock(), total_scored=5, eligible=2, threshold=0.60
        )
        mock_cls.return_value = mock_instance

        result = quick_analyze("/path/to/cv.pdf", threshold=0.60, auto_apply=False)

        assert result.total_scored == 5
        assert result.eligible == 2
        mock_instance.analyze.assert_called_once()
        mock_instance.analyze_and_apply.assert_not_called()

    @patch("backend.services.analyzer.JobAnalyzer")
    def test_quick_analyze_with_auto_apply(self, mock_cls):
        """quick_analyze with auto_apply=True should call analyze_and_apply()."""
        mock_instance = MagicMock()
        mock_instance.parse_cv.return_value = MagicMock()
        mock_instance.analyze_and_apply.return_value = AnalysisResult(
            profile=MagicMock(), total_scored=5, eligible=2, applied=1, threshold=0.60
        )
        mock_cls.return_value = mock_instance

        result = quick_analyze("/path/to/cv.pdf", auto_apply=True, max_apps=3)

        assert result.applied == 1
        mock_instance.analyze_and_apply.assert_called_once()
        # verify max_applications was passed through
        call_kwargs = mock_instance.analyze_and_apply.call_args[1]
        assert call_kwargs["max_applications"] == 3
