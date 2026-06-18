"""
Tests for the Cover Letter Generator.
"""

from __future__ import annotations

import pytest

from backend.models.profile import CandidateProfile, JobPosting, MatchResult, SeniorityLevel, Skill, Experience


class TestCoverLetterGenerator:
    """Tests for the cover letter generator (template fallback path)."""

    @pytest.fixture
    def profile(self) -> CandidateProfile:
        return CandidateProfile(
            full_name="Alex Chen",
            raw_text="Experienced Python developer",
            skills=[
                Skill(name="Python", category="language"),
                Skill(name="React", category="framework"),
                Skill(name="PostgreSQL", category="database"),
            ],
            experiences=[
                Experience(
                    company="TechCorp",
                    title="Senior Software Engineer",
                    description="Built scalable APIs serving 1M+ users",
                    start_date="2021",
                    end_date="Present",
                ),
            ],
            years_of_experience=6.0,
            seniority=SeniorityLevel.SENIOR,
        )

    @pytest.fixture
    def job(self) -> JobPosting:
        return JobPosting(
            title="Senior Backend Engineer",
            company="Stripe",
            description="Build payment infrastructure APIs with Python and PostgreSQL.",
            skills_required=["Python", "PostgreSQL", "Redis", "API Design"],
            location="San Francisco, CA",
            remote=True,
        )

    @pytest.fixture
    def match(self) -> MatchResult:
        return MatchResult(
            job=JobPosting(title="Senior Backend Engineer", company="Stripe"),
            score=0.82,
            skill_overlap=["Python", "PostgreSQL"],
            skill_gaps=["Redis", "API Design"],
            passed_threshold=True,
        )

    def test_generate_with_template_fallback(self, profile, job, match):
        """Test template-based fallback generation (no API keys needed)."""
        from backend.services.cover_letter_generator import CoverLetterGenerator
        gen = CoverLetterGenerator()

        letter = gen.generate(profile, job, match)
        assert isinstance(letter, str)
        assert len(letter) > 100
        assert "Stripe" in letter
        assert "Senior Backend Engineer" in letter
        assert "Alex Chen" in letter

    def test_generate_no_match(self, profile, job):
        """Test generation without a MatchResult."""
        from backend.services.cover_letter_generator import CoverLetterGenerator
        gen = CoverLetterGenerator()

        letter = gen.generate(profile, job)
        assert isinstance(letter, str)
        assert len(letter) > 100

    def test_generate_and_save(self, profile, job, match, tmp_path):
        """Test saving the cover letter to a file."""
        from backend.services.cover_letter_generator import CoverLetterGenerator
        gen = CoverLetterGenerator()

        output_path = gen.generate_and_save(profile, job, match, output_dir=tmp_path)
        assert output_path.exists()
        content = output_path.read_text()
        assert len(content) > 100

    def test_build_prompt_includes_cv_and_job(self, profile, job):
        """Test the prompt builder produces a comprehensive prompt."""
        from backend.services.cover_letter_generator import CoverLetterGenerator
        gen = CoverLetterGenerator()

        prompt = gen._build_prompt(profile, job)
        assert "CANDIDATE PROFILE" in prompt
        assert "JOB POSTING" in prompt
        assert "Stripe" in prompt
        assert "Python" in prompt
        assert "TechCorp" in prompt

    def test_different_tones(self, profile, job):
        """Test that tone parameter is accepted (only affects API call)."""
        from backend.services.cover_letter_generator import CoverLetterGenerator
        gen = CoverLetterGenerator()

        for tone in ["professional", "startup", "creative"]:
            letter = gen.generate(profile, job, tone=tone)
            assert len(letter) > 100

    def test_empty_profile(self, job):
        """Test edge case: empty profile."""
        from backend.services.cover_letter_generator import CoverLetterGenerator
        gen = CoverLetterGenerator()

        empty = CandidateProfile(full_name="Test")
        letter = gen.generate(empty, job)
        assert isinstance(letter, str)
        assert len(letter) > 50
