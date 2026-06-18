"""
CAPTCHA Detector — identifies CAPTCHA challenges on job application pages.

Detection strategies:
  1. DOM element detection (reCAPTCHA iframes, hCaptcha containers)
  2. Text pattern matching ("I'm not a robot", "verify you are human")
  3. Hidden input field detection (g-recaptcha-response)
  4. Image CAPTCHA detection (distorted text images)

Returns a CaptchaResult with type, confidence, and a screenshot suggestion.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CaptchaType(str, Enum):
    """Types of CAPTCHA challenges the detector can identify."""

    RECAPTCHA_V2 = "recaptcha_v2"          # "I'm not a robot" checkbox
    RECAPTCHA_V3 = "recaptcha_v3"          # Invisible / scored
    RECAPTCHA_ENTERPRISE = "recaptcha_enterprise"
    HCAPTCHA = "hcaptcha"
    TEXT_CAPTCHA = "text_captcha"           # Distorted text image
    IMAGE_CAPTCHA = "image_captcha"         # Select all images with X
    MATH_CAPTCHA = "math_captcha"           # Simple math problem
    CUSTOM_CAPTCHA = "custom_captcha"       # Custom implementation
    UNKNOWN = "unknown"


@dataclass
class CaptchaResult:
    """Result of a CAPTCHA detection attempt."""

    detected: bool = False
    captcha_type: CaptchaType = CaptchaType.UNKNOWN
    confidence: float = 0.0
    selector: str = ""                      # CSS selector for the CAPTCHA element
    frame_url: Optional[str] = None         # Source URL if inside an iframe
    screenshot_path: Optional[str] = None   # Path to a screenshot for human review
    details: str = ""


# ─── Detection patterns ─────────────────────────────────────────────────────

RECAPTCHA_SELECTORS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='google.com/recaptcha']",
    ".g-recaptcha",
    "#g-recaptcha",
    "div[data-sitekey]",
    "textarea#g-recaptcha-response",
    "input[name='g-recaptcha-response']",
]

HCAPTCHA_SELECTORS = [
    "iframe[src*='hcaptcha.com']",
    ".h-captcha",
    "div[data-hcaptcha-widget-id]",
]

COMMON_CAPTCHA_KEYWORDS = re.compile(
    r"(captcha|i'm not a robot|verify you are human|"
    r"security check|bot detection|"
    r"please prove you are human|"
    r"enter the text you see|"
    r"select all (images with|squares with)|"
    r"type the characters)",
    re.I,
)

CUSTOM_CAPTCHA_PATTERNS = [
    re.compile(r"captcha_img|captcha_image|captcha_code", re.I),
    re.compile(r"data:image.*base64.*captcha", re.I),
    re.compile(r"src=[\"'].*captcha.*\.(png|jpg|jpeg|gif|svg)[\"']", re.I),
]


class CaptchaDetector:
    """Detects CAPTCHAs on a page using DOM inspection and text analysis."""

    def detect(self, page) -> CaptchaResult:
        """
        Inspect the given Playwright page for CAPTCHA challenges.

        Args:
            page: A Playwright Page object.

        Returns:
            CaptchaResult with detection status and details.
        """
        # Strategy 1: Check for reCAPTCHA iframes / elements
        for selector in RECAPTCHA_SELECTORS:
            try:
                el = page.query_selector(selector)
                if el:
                    frame_url = None
                    if el.tag_name == "iframe":
                        frame_url = el.get_attribute("src")
                    return CaptchaResult(
                        detected=True,
                        captcha_type=CaptchaType.RECAPTCHA_V2,
                        confidence=0.95,
                        selector=selector,
                        frame_url=frame_url,
                        details="reCAPTCHA v2 element detected on page",
                    )
            except Exception:
                continue

        # Strategy 2: Check for hCaptcha elements
        for selector in HCAPTCHA_SELECTORS:
            try:
                el = page.query_selector(selector)
                if el:
                    frame_url = None
                    if el.tag_name == "iframe":
                        frame_url = el.get_attribute("src")
                    return CaptchaResult(
                        detected=True,
                        captcha_type=CaptchaType.HCAPTCHA,
                        confidence=0.95,
                        selector=selector,
                        frame_url=frame_url,
                        details="hCaptcha element detected on page",
                    )
            except Exception:
                continue

        # Strategy 3: Search page text for CAPTCHA keywords
        try:
            body_text = page.inner_text("body") or ""
            match = COMMON_CAPTCHA_KEYWORDS.search(body_text)
            if match:
                return CaptchaResult(
                    detected=True,
                    captcha_type=CaptchaType.UNKNOWN,
                    confidence=0.7,
                    details=f"CAPTCHA keyword matched: '{match.group(0)}'",
                )
        except Exception:
            pass

        # Strategy 4: Check page source for custom CAPTCHA patterns
        try:
            html = page.content() or ""
            for pat in CUSTOM_CAPTCHA_PATTERNS:
                if pat.search(html):
                    return CaptchaResult(
                        detected=True,
                        captcha_type=CaptchaType.CUSTOM_CAPTCHA,
                        confidence=0.6,
                        details="Custom CAPTCHA pattern matched in page source",
                    )
        except Exception:
            pass

        # Strategy 5: Check for invisible reCAPTCHA v3
        try:
            has_recaptcha_api = page.evaluate(
                "typeof window.grecaptcha !== 'undefined'"
            )
            if has_recaptcha_api:
                return CaptchaResult(
                    detected=True,
                    captcha_type=CaptchaType.RECAPTCHA_V3,
                    confidence=0.8,
                    details="reCAPTCHA v3 API detected in window scope",
                )
        except Exception:
            pass

        return CaptchaResult(
            detected=False,
            confidence=0.0,
            details="No CAPTCHA detected on page",
        )

    def take_screenshot(self, page, output_path: str) -> Optional[str]:
        """Capture a screenshot of the page for human review."""
        try:
            page.screenshot(path=output_path, full_page=True)
            logger.info("Screenshot saved: %s", output_path)
            return output_path
        except Exception as e:
            logger.warning("Failed to take screenshot: %s", e)
            return None
