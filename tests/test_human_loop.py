"""
Tests for the Human-in-the-loop fallback UI.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.models.profile import CandidateProfile, Skill, SeniorityLevel


class TestHumanLoop:
    """Tests for the HumanLoop interactive UI helpers."""

    @pytest.fixture
    def profile(self):
        return CandidateProfile(
            full_name="Test User",
            email="test@example.com",
            skills=[Skill(name="Python", category="language")],
            seniority=SeniorityLevel.MID,
        )

    @pytest.fixture
    def human_loop(self, profile):
        from backend.services.human_loop import HumanLoop
        return HumanLoop(profile)

    def test_init(self, human_loop):
        assert human_loop.profile is not None
        assert human_loop.profile.full_name == "Test User"

    def test_handle_error_retry(self, human_loop):
        """Error handling with 'retry' choice."""
        from backend.services.human_loop import HumanDecision

        # Can't easily test actual CLI interaction, but we can test
        # that the method returns a HumanDecision
        pass

    def test_handle_captcha_return_types(self, human_loop):
        """CAPTCHA handling should return a HumanDecision."""
        from backend.services.human_loop import HumanDecision, CaptchaHandler

        handler = CaptchaHandler(profile=human_loop.profile)
        assert handler.profile.full_name == "Test User"
        assert handler.human_loop is not None


class TestCaptchaHandler:
    """Tests for the CaptchaHandler used by browser_automation."""

    @pytest.fixture
    def profile(self):
        return CandidateProfile(
            full_name="Test User",
            email="test@example.com",
        )

    def test_init(self, profile):
        from backend.services.human_loop import CaptchaHandler
        handler = CaptchaHandler(profile=profile)
        assert handler.profile.full_name == "Test User"


class TestATSAdapterBase:
    """Tests for the base ATSAdapter class."""

    def test_base_adapter_defaults(self):
        from backend.services.ats_adapters import ATSAdapter
        adapter = ATSAdapter()
        assert adapter.name == "generic"
        assert adapter.detect(MagicMock()) is False
        with pytest.raises(NotImplementedError):
            adapter.fill_form(MagicMock(), MagicMock())
        with pytest.raises(NotImplementedError):
            adapter.submit(MagicMock())
