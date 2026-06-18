"""
Tests for the Semantic Matching Engine.
"""

from __future__ import annotations

import pytest

from backend.models.profile import CandidateProfile, JobPosting, SeniorityLevel, Skill, Experience


class TestSemanticMatcher:
    """Tests for the SemanticMatcher scoring logic."""

    @pytest.fixture
    def profile(self) -> CandidateProfile:
        return CandidateProfile(
            full_name="Test User",
            raw_text="Python developer with React and PostgreSQL experience",
            skills=[
                Skill(name="Python", category="language", confidence=0.9),
                Skill(name="React", category="framework", confidence=0.8),
                Skill(name="PostgreSQL", category="database", confidence=0.7),
                Skill(name="Docker", category="cloud", confidence=0.6),
                Skill(name="AWS", category="cloud", confidence=0.5),
            ],
            experiences=[
                Experience(company="Acme", title="Software Engineer", description="Built APIs")
            ],
            years_of_experience=5.0,
            seniority=SeniorityLevel.SENIOR,
        )

    @pytest.fixture
    def matcher(self):
        from backend.services.matcher import SemanticMatcher
        return SemanticMatcher(threshold=0.5)

    def test_skill_score_perfect_match(self, matcher, profile):
        job = JobPosting(
            title="Python Developer",
            company="TestCo",
            description="Python and React role",
            skills_required=["Python", "React", "PostgreSQL", "Docker", "AWS"],
        )
        score, overlap, gap = matcher._skill_score(profile, job)
        assert score == 1.0  # all 5 skills match
        assert len(overlap) == 5
        assert len(gap) == 0

    def test_skill_score_partial_match(self, matcher, profile):
        job = JobPosting(
            title="Go Developer",
            company="TestCo",
            description="Go role",
            skills_required=["Go", "Kubernetes", "Python"],
        )
        score, overlap, gap = matcher._skill_score(profile, job)
        assert score == pytest.approx(1 / 3, rel=0.01)
        assert overlap == ["python"]
        assert gap == ["go", "kubernetes"]

    def test_skill_score_no_match(self, matcher, profile):
        job = JobPosting(
            title="Rust Engineer",
            company="TestCo",
            description="Rust role",
            skills_required=["Rust", "C++"],
        )
        score, overlap, gap = matcher._skill_score(profile, job)
        assert score == 0.0
        assert len(overlap) == 0
        assert len(gap) == 2

    def test_seniority_score_exact_match(self, matcher, profile):
        job = JobPosting(
            title="Senior Engineer",
            company="TestCo",
            description="Senior role",
            seniority=SeniorityLevel.SENIOR,
        )
        score, match = matcher._seniority_score(profile, job)
        assert score == 1.0
        assert match is True

    def test_seniority_score_close(self, matcher, profile):
        job = JobPosting(
            title="Staff Engineer",
            company="TestCo",
            description="Staff role",
            seniority=SeniorityLevel.STAFF,
        )
        score, match = matcher._seniority_score(profile, job)
        assert score == 0.8
        assert match is True

    def test_seniority_score_too_far(self, matcher, profile):
        job = JobPosting(
            title="Entry Level Developer",
            company="TestCo",
            description="Entry role",
            seniority=SeniorityLevel.ENTRY,
        )
        score, match = matcher._seniority_score(profile, job)
        assert score == 0.0
        assert match is False

    def test_location_score_remote_preferred(self, matcher, profile):
        profile.remote_preferred = True
        job = JobPosting(title="Remote Dev", company="TestCo", remote=True)
        score = matcher._location_score(profile, job)
        assert score == 1.0

    def test_location_score_match(self, matcher, profile):
        profile.preferred_locations = ["San Francisco"]
        job = JobPosting(title="Dev", company="TestCo", location="San Francisco, CA")
        score = matcher._location_score(profile, job)
        assert score == 1.0

    def test_location_score_mismatch(self, matcher, profile):
        profile.preferred_locations = ["New York"]
        job = JobPosting(title="Dev", company="TestCo", location="Los Angeles")
        score = matcher._location_score(profile, job)
        assert score < 0.5

    def test_composite_score(self, matcher, profile):
        """Integration test: full composite score."""
        job = JobPosting(
            title="Senior Python Developer",
            company="TechCo",
            description="Python, React, PostgreSQL role",
            skills_required=["Python", "React", "PostgreSQL"],
            seniority=SeniorityLevel.SENIOR,
            location="San Francisco",
            remote=False,
        )
        result = matcher.score(profile, job)
        assert 0.0 <= result.score <= 1.0
        assert isinstance(result.skill_overlap, list)
        assert isinstance(result.skill_gaps, list)
        assert result.reasoning

    def test_rank_returns_sorted(self, matcher, profile):
        jobs = [
            JobPosting(title="Best Match", company="A", skills_required=["Python", "React"], seniority=SeniorityLevel.SENIOR),
            JobPosting(title="Worst Match", company="B", skills_required=["Rust", "C++"], seniority=SeniorityLevel.ENTRY),
            JobPosting(title="Medium Match", company="C", skills_required=["Python"], seniority=SeniorityLevel.MID),
        ]
        results = matcher.rank(profile, jobs, top_k=5)
        assert len(results) == 3
        # Check they're sorted best to worst
        assert results[0].score >= results[1].score >= results[2].score

    def test_shortlist(self, matcher):
        from backend.models.profile import MatchResult, JobPosting
        passing = MatchResult(
            job=JobPosting(title="Good"),
            score=0.8,
            passed_threshold=True,
        )
        failing = MatchResult(
            job=JobPosting(title="Bad"),
            score=0.3,
            passed_threshold=False,
        )
        results = matcher.shortlist([passing, failing])
        assert len(results) == 1
        assert results[0].job.title == "Good"
