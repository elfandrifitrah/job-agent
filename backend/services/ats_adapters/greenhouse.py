"""
Greenhouse ATS Adapter — form filling for Greenhouse-powered career pages.

Greenhouse uses a predictable DOM structure with data attributes:
  - Fields use data attributes like data-field-id, data-field-name
  - Standard fields: name, email, phone, resume, cover_letter, location
  - Radio/select for dropdowns
  - File upload for resume

References:
  - https://support.greenhouse.io/hc/en-us/articles/360027829312-Job-Board-API
  - Greenhouse job board pages use .board-container and .application-form
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from backend.services.ats_adapters import ATSAdapter

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from backend.models.profile import CandidateProfile

logger = logging.getLogger(__name__)


class GreenhouseAdapter(ATSAdapter):
    """Adapter for Greenhouse-powered application forms."""

    name = "greenhouse"

    # Greenhouse-specific field name → profile attribute mapping
    FIELD_MAP = {
        "first_name": ("full_name", lambda p: p.full_name.split()[0] if p.full_name else ""),
        "last_name": ("full_name", lambda p: p.full_name.split()[-1] if p.full_name and len(p.full_name.split()) > 1 else ""),
        "name": "full_name",
        "email": "email",
        "phone": "phone",
        "location": ("location", lambda p: p.location or (p.preferred_locations[0] if p.preferred_locations else "")),
        "cover_letter": "cover_letter_text",
        "linkedin": "linkedin_url",
        "github": "github_url",
        "website": "portfolio_url",
        "job_title": ("current_title", lambda p: p.experiences[0].title if p.experiences else ""),
        "current_company": ("current_company", lambda p: p.experiences[0].company if p.experiences else ""),
        "school": ("education_text", lambda p: p.education[0].institution if p.education else ""),
        "degree": ("education_text", lambda p: p.education[0].degree if p.education else ""),
    }

    # Common Greenhouse selectors for text fields
    TEXT_FIELD_SELECTORS = [
        "input[name='{field}']",
        "input[id*='{field}']",
        "input[data-field-name='{field}']",
        "textarea[name='{field}']",
        "textarea[id*='{field}']",
    ]

    def detect(self, page: "Page") -> bool:
        """Check if the page is a Greenhouse job board."""
        try:
            url = page.url.lower()
            if "greenhouse.io" in url or "boards.greenhouse.io" in url:
                return True

            # Check for Greenhouse-specific DOM indicators
            indicators = [
                page.query_selector(".board-container"),
                page.query_selector(".application-form"),
                page.query_selector("[data-application-form]"),
                page.query_selector("link[href*='greenhouse']"),
            ]
            return any(bool(i) for i in indicators)
        except Exception:
            return False

    def fill_form(self, page: "Page", profile: "CandidateProfile", cv_path: str = "") -> bool:
        """Fill the Greenhouse application form."""
        filled = 0

        # Handle the "Apply Now" interstitial if present
        self._click_apply_now(page)

        # Fill text fields
        for gh_field, profile_attr in self.FIELD_MAP.items():
            value = self._get_profile_value(profile, profile_attr)
            if not value:
                continue

            # Try each selector pattern
            for sel_template in self.TEXT_FIELD_SELECTORS:
                selector = sel_template.format(field=gh_field)
                try:
                    el = page.query_selector(selector)
                    if el and el.is_visible():
                        el.click()
                        el.fill("")
                        el.fill(str(value))
                        filled += 1
                        logger.debug("Greenhouse: filled %s = '%s'", gh_field, str(value)[:40])
                        break
                except Exception:
                    continue

        # Try data-attribute-based field detection for any remaining fields
        try:
            data_fields = page.query_selector_all("[data-field-name]")
            for el in data_fields:
                field_name = el.get_attribute("data-field-name") or ""
                if field_name and field_name not in [k for k in self.FIELD_MAP]:
                    logger.debug("Greenhouse: unknown data-field '%s', skipping", field_name)
        except Exception:
            pass

        # Upload resume (CV)
        if cv_path:
            try:
                file_input = page.query_selector("input[type=file]")
                if file_input:
                    file_input.set_input_files(cv_path)
                    logger.info("Greenhouse: resume uploaded")
                    filled += 1
            except Exception as e:
                logger.warning("Greenhouse: resume upload failed: %s", e)

        logger.info("Greenhouse: filled %d fields", filled)
        return filled > 0

    def submit(self, page: "Page") -> bool:
        """Submit the Greenhouse application."""
        submit_selectors = [
            "button[type=submit]",
            "button:has-text('Submit Application')",
            "button:has-text('Submit')",
            ".submit-application",
            "#submit-application",
            "[data-action=submit]",
        ]
        for sel in submit_selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    logger.info("Greenhouse: application submitted")
                    return True
            except Exception:
                continue
        return False

    def _click_apply_now(self, page: "Page") -> None:
        """Click the 'Apply Now' button if visible."""
        try:
            apply_btn = page.query_selector("button:has-text('Apply Now'), a:has-text('Apply Now')")
            if apply_btn and apply_btn.is_visible():
                apply_btn.click()
                logger.debug("Greenhouse: clicked 'Apply Now'")
        except Exception:
            pass

    def _get_profile_value(self, profile: "CandidateProfile", attr) -> str:
        """Extract a value from the profile based on the mapping."""
        if isinstance(attr, tuple):
            field_name, transformer = attr
            if field_name == "cover_letter_text":
                return ""
            return str(transformer(profile)) if transformer else ""
        elif attr == "cover_letter_text":
            return ""
        else:
            return str(getattr(profile, attr, "") or "")
