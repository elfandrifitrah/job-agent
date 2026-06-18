"""
Tests for the CAPTCHA Detector.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.services.captcha_detector import CaptchaDetector, CaptchaType


class TestCaptchaDetector:
    """Tests for the CAPTCHA detection service (no browser needed)."""

    @pytest.fixture
    def detector(self):
        return CaptchaDetector()

    def test_no_captcha(self, detector):
        """Page without CAPTCHA elements should return not detected."""
        page = MagicMock()
        page.query_selector.return_value = None
        page.inner_text.return_value = "Welcome to the application form"
        page.content.return_value = "<html><body>Simple form</body></html>"
        page.evaluate.return_value = False

        result = detector.detect(page)
        assert result.detected is False
        assert result.confidence == 0.0

    def test_recaptcha_v2_detected(self, detector):
        """reCAPTCHA v2 iframe should be detected."""
        page = MagicMock()
        # Simulate reCAPTCHA iframe detection
        iframe_mock = MagicMock()
        iframe_mock.tag_name = "iframe"
        iframe_mock.get_attribute.return_value = "https://www.google.com/recaptcha/api2/anchor"
        page.query_selector.side_effect = lambda sel: iframe_mock if "recaptcha" in sel else None

        result = detector.detect(page)
        assert result.detected is True
        assert result.captcha_type == CaptchaType.RECAPTCHA_V2
        assert result.confidence >= 0.9

    def test_hcaptcha_detected(self, detector):
        """hCaptcha element should be detected."""
        page = MagicMock()
        hcaptcha_iframe = MagicMock()
        hcaptcha_iframe.tag_name = "iframe"
        hcaptcha_iframe.get_attribute.return_value = "https://hcaptcha.com/1/api.js"
        page.query_selector.side_effect = lambda sel: hcaptcha_iframe if "hcaptcha" in sel else None

        result = detector.detect(page)
        assert result.detected is True
        assert result.captcha_type == CaptchaType.HCAPTCHA

    def test_captcha_keyword_detected(self, detector):
        """Text keywords like 'I'm not a robot' should trigger detection."""
        page = MagicMock()
        page.query_selector.return_value = None  # No iframe
        page.inner_text.return_value = "Please verify you are human before continuing"
        page.content.return_value = "<html><body>verify you are human</body></html>"
        page.evaluate.return_value = False

        result = detector.detect(page)
        assert result.detected is True
        assert "verify" in result.details.lower()

    def test_recaptcha_v3_detected(self, detector):
        """reCAPTCHA v3 (invisible, via JS API) should be detected."""
        page = MagicMock()
        page.query_selector.return_value = None
        page.inner_text.return_value = "Apply now"
        page.content.return_value = "<html><body>Job application</body></html>"

        def evaluate_side_effect(script):
            if "typeof window.grecaptcha" in script:
                return True
            return False
        page.evaluate.side_effect = evaluate_side_effect

        result = detector.detect(page)
        assert result.detected is True
        assert result.captcha_type == CaptchaType.RECAPTCHA_V3

    def test_take_screenshot(self, detector, tmp_path):
        """Screenshot should be saved to the specified path."""
        page = MagicMock()
        ss_path = str(tmp_path / "captcha_test.png")

        result_path = detector.take_screenshot(page, ss_path)
        assert result_path == ss_path
        page.screenshot.assert_called_once_with(path=ss_path, full_page=True)

    def test_custom_captcha_pattern(self, detector):
        """Custom CAPTCHA image patterns in HTML should be detected."""
        page = MagicMock()
        page.query_selector.return_value = None
        page.inner_text.return_value = "Enter the code"
        page.content.return_value = '<html><body><img src="captcha_image.png" /></body></html>'
        page.evaluate.return_value = False

        result = detector.detect(page)
        assert result.detected is True
