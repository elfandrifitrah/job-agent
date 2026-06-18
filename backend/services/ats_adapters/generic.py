"""
Generic ATS Adapter — heuristic-based form filling for unknown applicant tracking systems.

Works by detecting form fields via common CSS selectors and filling them
based on field labels, placeholders, and autocomplete attributes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.services.ats_adapters import ATSAdapter

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from backend.models.profile import CandidateProfile

logger = logging.getLogger(__name__)


class GenericAdapter(ATSAdapter):
    """Fallback adapter for unknown ATS platforms — uses generic form detection."""

    name = "generic"

    def detect(self, page: "Page") -> bool:
        """Generic adapter matches any page with form elements."""
        try:
            # Check for common form indicators
            has_form = page.query_selector("form") is not None
            has_inputs = page.query_selector("input, textarea, select") is not None
            return has_form or has_inputs
        except Exception:
            return False

    def fill_form(self, page: "Page", profile: "CandidateProfile", cv_path: str = "") -> bool:
        """Use the generic FormDetector and FormFiller to fill all fields."""
        from backend.services.browser_automation import FormDetector, FormFiller

        detector = FormDetector()
        filler = FormFiller(profile)

        fields = detector.detect_fields(page)
        if not fields:
            logger.warning("GenericAdapter: no fields detected")
            return False

        filled = filler.fill_fields(page, fields)
        logger.info("GenericAdapter: filled %d/%d fields", filled, len(fields))

        # Upload CV if provided
        if cv_path:
            try:
                file_input = page.query_selector("input[type=file]")
                if file_input:
                    file_input.set_input_files(cv_path)
                    logger.info("GenericAdapter: uploaded CV")
            except Exception as e:
                logger.warning("GenericAdapter: file upload failed: %s", e)

        return filled > 0

    def submit(self, page: "Page") -> bool:
        """Find and click the submit button."""
        submit_selectors = [
            "button[type=submit]",
            "input[type=submit]",
            "button:has-text('Submit')",
            "button:has-text('Submit Application')",
            "button:has-text('Send')",
            "button:has-text('Apply')",
        ]
        for sel in submit_selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    return True
            except Exception:
                continue
        return False
