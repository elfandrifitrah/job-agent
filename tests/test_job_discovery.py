"""
Tests for the Job Discovery service.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.models.profile import SeniorityLevel


class TestJobPostingNormalisation:
    """Tests for the JobSource base normalisation logic."""

    @pytest.fixture
    def source(self):
        from backend.services.job_discovery import AdzunaSource
        return AdzunaSource()

    def test_normalise_creates_id(self, source):
        job = source.normalise(
            title="Software Engineer",
            company="Google",
            description="Build things",
        )
        assert job.id
        assert len(job.id) == 12
        assert job.source == "adzuna"

    def test_normalise_seniority_senior(self, source):
        job = source.normalise(
            title="Senior Software Engineer",
            company="Google",
            description="Lead team of engineers",
        )
        assert job.seniority == SeniorityLevel.SENIOR

    def test_normalise_seniority_junior(self, source):
        job = source.normalise(
            title="Junior Developer",
            company="Startup",
            description="Entry-level position",
        )
        assert job.seniority == SeniorityLevel.JUNIOR

    def test_normalise_seniority_from_description(self, source):
        job = source.normalise(
            title="Engineer",
            company="Co",
            description="This is a principal engineer role",
        )
        assert job.seniority == SeniorityLevel.PRINCIPAL

    def test_normalise_seniority_unknown(self, source):
        job = source.normalise(
            title="Engineer",
            company="Co",
            description="General engineering position",
        )
        assert job.seniority == SeniorityLevel.UNKNOWN


class TestSearchParams:
    """Tests for SearchParams dataclass."""

    def test_default_params(self):
        from backend.services.job_discovery import SearchParams
        p = SearchParams()
        assert p.role == ""
        assert p.max_results == 20
        assert p.days_old == 14
        assert p.remote is False


class TestJobDiscovery:
    """Integration tests for the JobDiscovery orchestrator (no API calls)."""

    @pytest.fixture
    def discovery(self):
        from backend.services.job_discovery import JobDiscovery
        return JobDiscovery()

    def test_search_with_no_api_keys(self, discovery):
        """Without API keys configured, sources should gracefully skip."""
        from backend.services.job_discovery import SearchParams
        result = discovery.search(SearchParams(role="Engineer", max_results=5))
        # Without keys, LinkedIn and Indeed will skip.
        # Adzuna will fail gracefully (no keys).
        assert isinstance(result.jobs, list)
        assert isinstance(result.source_counts, dict)
        # Should not crash — gracefully handles missing config
        assert len(result.errors) <= len(discovery.sources)
