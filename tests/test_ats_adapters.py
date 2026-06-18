"""
Tests for ATS adapters — detection, field mapping, and submission.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.models.profile import CandidateProfile, Skill, Experience, SeniorityLevel


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def profile():
    return CandidateProfile(
        full_name="Alex Chen",
        email="alex@example.com",
        phone="+1-555-123-4567",
        linkedin_url="https://linkedin.com/in/alexchen",
        github_url="https://github.com/alexchen",
        portfolio_url="https://alexchen.dev",
        location="San Francisco, CA",
        skills=[Skill(name="Python", category="language")],
        experiences=[Experience(company="TechCorp", title="Senior Engineer")],
        years_of_experience=6.0,
        seniority=SeniorityLevel.SENIOR,
    )


# ─── Generic Adapter ─────────────────────────────────────────────────────────

class TestGenericAdapter:
    @pytest.fixture
    def adapter(self):
        from backend.services.ats_adapters.generic import GenericAdapter
        return GenericAdapter()

    def test_detect_with_form(self, adapter):
        page = MagicMock()
        page.query_selector.side_effect = lambda sel: MagicMock() if sel == "form" else None
        assert adapter.detect(page) is True

    def test_detect_with_inputs(self, adapter):
        page = MagicMock()
        page.query_selector.side_effect = lambda sel: MagicMock() if sel in ("form", "input, textarea, select") else None
        assert adapter.detect(page) is True

    def test_detect_empty_page(self, adapter):
        page = MagicMock()
        page.query_selector.return_value = None
        assert adapter.detect(page) is False

    def test_fill_form_no_fields(self, adapter):
        page = MagicMock()
        page.query_selector_all.return_value = []
        result = adapter.fill_form(page, MagicMock())
        assert result is False

    def test_submit_no_button(self, adapter):
        page = MagicMock()
        page.query_selector.return_value = None
        assert adapter.submit(page) is False

    def test_submit_finds_button(self, adapter):
        page = MagicMock()
        btn = MagicMock()
        btn.is_visible.return_value = True
        page.query_selector.return_value = btn
        assert adapter.submit(page) is True


# ─── Greenhouse Adapter ──────────────────────────────────────────────────────

class TestGreenhouseAdapter:
    @pytest.fixture
    def adapter(self):
        from backend.services.ats_adapters.greenhouse import GreenhouseAdapter
        return GreenhouseAdapter()

    def test_detect_by_url(self, adapter):
        page = MagicMock()
        page.url = "https://boards.greenhouse.io/company/jobs/123"
        assert adapter.detect(page) is True

    def test_detect_by_dom(self, adapter):
        page = MagicMock()
        page.url = "https://example.com/careers"
        page.query_selector.side_effect = lambda sel: MagicMock() if "board-container" in sel else None
        assert adapter.detect(page) is True

    def test_detect_not_greenhouse(self, adapter):
        page = MagicMock()
        page.url = "https://example.com"
        page.query_selector.return_value = None
        assert adapter.detect(page) is False

    def test_get_profile_value_name(self, adapter, profile):
        val = adapter._get_profile_value(profile, "full_name")
        assert val == "Alex Chen"

    def test_get_profile_value_email(self, adapter, profile):
        val = adapter._get_profile_value(profile, "email")
        assert val == "alex@example.com"

    def test_get_profile_value_with_transformer(self, adapter, profile):
        val = adapter._get_profile_value(profile, ("current_title", lambda p: p.experiences[0].title if p.experiences else ""))
        assert val == "Senior Engineer"

    def test_fill_form_fills_fields(self, adapter, profile):
        page = MagicMock()
        # Make query_selector return a mock element for field lookups
        mock_el = MagicMock()
        mock_el.is_visible.return_value = True
        page.query_selector.return_value = mock_el
        # No file input
        page.query_selector_all.return_value = []

        result = adapter.fill_form(page, profile, "")
        assert result is True  # Fills fields from FIELD_MAP

    def test_submit_found(self, adapter):
        page = MagicMock()
        btn = MagicMock()
        btn.is_visible.return_value = True
        page.query_selector.return_value = btn
        assert adapter.submit(page) is True


# ─── Lever Adapter ───────────────────────────────────────────────────────────

class TestLeverAdapter:
    @pytest.fixture
    def adapter(self):
        from backend.services.ats_adapters.lever import LeverAdapter
        return LeverAdapter()

    def test_detect_by_url(self, adapter):
        page = MagicMock()
        page.url = "https://jobs.lever.co/company/role-123"
        assert adapter.detect(page) is True

    def test_detect_by_dom(self, adapter):
        page = MagicMock()
        page.url = "https://example.com"
        page.query_selector.side_effect = lambda sel: MagicMock() if "application-form" in sel else None
        assert adapter.detect(page) is True

    def test_get_profile_value(self, adapter, profile):
        val = adapter._get_profile_value(profile, "full_name")
        assert val == "Alex Chen"

    def test_get_profile_value_with_transformer(self, adapter, profile):
        val = adapter._get_profile_value(profile, ("current_company", lambda p: p.experiences[0].company if p.experiences else ""))
        assert val == "TechCorp"

    def test_fill_form_no_crash(self, adapter, profile):
        page = MagicMock()
        page.query_selector.return_value = None
        page.query_selector_all.return_value = []

        result = adapter.fill_form(page, profile, "")
        assert isinstance(result, bool)

    def test_submit_not_found(self, adapter):
        page = MagicMock()
        page.query_selector.return_value = None
        assert adapter.submit(page) is False


# ─── Workday Adapter ─────────────────────────────────────────────────────────

class TestWorkdayAdapter:
    @pytest.fixture
    def adapter(self):
        from backend.services.ats_adapters.workday import WorkdayAdapter
        return WorkdayAdapter()

    def test_detect_by_url(self, adapter):
        page = MagicMock()
        page.url = "https://wd5.myworkdayjobs.com/en-US/company"
        assert adapter.detect(page) is True

    def test_detect_not_workday(self, adapter):
        page = MagicMock()
        page.url = "https://example.com"
        page.query_selector.return_value = None
        assert adapter.detect(page) is False

    def test_match_label_to_value_email(self, adapter, profile):
        val = adapter._match_label_to_value("email address", profile)
        assert val == "alex@example.com"

    def test_match_label_to_value_first_name(self, adapter, profile):
        val = adapter._match_label_to_value("first name", profile)
        assert val == "Alex"

    def test_match_label_to_value_last_name(self, adapter, profile):
        val = adapter._match_label_to_value("last name", profile)
        assert val == "Chen"

    def test_match_label_to_value_company(self, adapter, profile):
        val = adapter._match_label_to_value("current company", profile)
        assert val == "TechCorp"

    def test_match_label_to_value_location(self, adapter, profile):
        val = adapter._match_label_to_value("location", profile)
        assert val == "San Francisco, CA"

    def test_match_label_to_value_unknown(self, adapter, profile):
        val = adapter._match_label_to_value("favorite color", profile)
        assert val == ""

    def test_fill_form_no_crash(self, adapter, profile):
        page = MagicMock()
        page.query_selector.return_value = None
        page.query_selector_all.return_value = []
        page.evaluate.return_value = None

        result = adapter.fill_form(page, profile, "")
        assert isinstance(result, bool)

    def test_submit_not_found(self, adapter):
        page = MagicMock()
        page.query_selector.return_value = None
        assert adapter.submit(page) is False


# ─── ATS Registry ────────────────────────────────────────────────────────────

class TestATSRegistry:
    def test_get_adapter_greenhouse(self):
        from backend.services.ats_adapters import get_adapter
        adapter = get_adapter("https://boards.greenhouse.io/company/jobs/123")
        assert adapter.name == "greenhouse"

    def test_get_adapter_lever(self):
        from backend.services.ats_adapters import get_adapter
        adapter = get_adapter("https://jobs.lever.co/company/role")
        assert adapter.name == "lever"

    def test_get_adapter_workday(self):
        from backend.services.ats_adapters import get_adapter
        adapter = get_adapter("https://wd5.myworkdayjobs.com/company")
        assert adapter.name == "workday"

    def test_get_adapter_unknown(self):
        from backend.services.ats_adapters import get_adapter
        adapter = get_adapter("https://example.com/careers")
        assert adapter.name == "generic"
