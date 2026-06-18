"""
Lever ATS Adapter — form filling for Lever-powered career pages.

Lever uses a predictable structure:
  - Application form at /apply or embedded on the job page
  - Fields use name attributes like name, email, phone, etc.
  - Uses a multi-step form with "Next" buttons
  - File upload for resume with drag-and-drop

References:
  - https://jobs.lever.co/ (common career page pattern)
  - Lever forms use .application-form and .application-field
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.services.ats_adapters import ATSAdapter

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from backend.models.profile import CandidateProfile

logger = logging.getLogger(__name__)


class LeverAdapter(ATSAdapter):
    """Adapter for Lever-powered application forms."""

    name = "lever"

    # Lever field name → profile attribute mapping
    FIELD_MAP = {
        "name": "full_name",
        "first": ("full_name", lambda p: p.full_name.split()[0] if p.full_name else ""),
        "last": ("full_name", lambda p: p.full_name.split()[-1] if p.full_name and len(p.full_name.split()) > 1 else ""),
        "email": "email",
        "phone": "phone",
        "org": ("current_company", lambda p: p.experiences[0].company if p.experiences else ""),
        "linkedin": "linkedin_url",
        "github": "github_url",
        "url": "portfolio_url",
        "urls": "portfolio_url",
        "location": ("location", lambda p: p.location or (p.preferred_locations[0] if p.preferred_locations else "")),
        "resume": "cv_file",
        "cover": "cover_letter_file",
    }

    # Lever-specific selectors
    TEXT_FIELD_SELECTORS = [
        "input[name='{field}']",
        "input[id*='{field}']",
        "input[placeholder*='{field}' i]",
        "textarea[name='{field}']",
    ]

    def detect(self, page: "Page") -> bool:
        """Check if the page is a Lever job board."""
        try:
            url = page.url.lower()
            if "lever.co" in url or "jobs.lever.co" in url:
                return True

            # Check for Lever-specific DOM indicators
            indicators = [
                page.query_selector(".application-form"),
                page.query_selector("[data-application-form]"),
                page.query_selector(".lever-apply-form"),
                page.query_selector("link[href*='lever']"),
            ]
            return any(bool(i) for i in indicators)
        except Exception:
            return False

    def fill_form(self, page: "Page", profile: "CandidateProfile", cv_path: str = "") -> bool:
        """Fill the Lever application form, stepping through multi-step forms."""
        filled = 0

        # Click initial apply button if present
        self._click_apply(page)

        # Lever forms often have multiple steps — fill what we can on each
        max_steps = 5
        for step in range(max_steps):
            # Fill text fields on current step
            step_filled = self._fill_visible_fields(page, profile)
            filled += step_filled

            if step_filled > 0:
                logger.debug("Lever step %d: filled %d fields", step + 1, step_filled)

            # Upload resume if available
            if step == 0 and cv_path:
                try:
                    file_input = page.query_selector("input[type=file]")
                    if file_input:
                        file_input.set_input_files(cv_path)
                        logger.info("Lever: resume uploaded")
                        filled += 1
                except Exception as e:
                    logger.warning("Lever: resume upload failed: %s", e)

            # Try to click "Next" or continue to next step
            if not self._click_next(page):
                break

        logger.info("Lever: filled %d fields across %d steps", filled, step + 1)
        return filled > 0

    def submit(self, page: "Page") -> bool:
        """Submit the Lever application."""
        submit_selectors = [
            "button[type=submit]",
            "button:has-text('Submit')",
            "button:has-text('Submit Application')",
            "button:has-text('Send Application')",
            ".submit-application",
            "[data-action=submit]",
        ]
        for sel in submit_selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    logger.info("Lever: application submitted")
                    return True
            except Exception:
                continue
        return False

    def _click_apply(self, page: "Page") -> None:
        """Click the initial apply button."""
        try:
            selectors = [
                "a:has-text('Apply for this job')",
                "a:has-text('Apply')",
                "button:has-text('Apply')",
                ".apply-button",
                "#apply-button",
            ]
            for sel in selectors:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    logger.debug("Lever: clicked apply button")
                    return
        except Exception:
            pass

    def _click_next(self, page: "Page") -> bool:
        """Click the 'Next' button to advance to the next form step."""
        try:
            next_selectors = [
                "button:has-text('Next')",
                "button:has-text('Continue')",
                "button:has-text('Next Step')",
                "[data-testid='next-button']",
            ]
            for sel in next_selectors:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    logger.debug("Lever: clicked 'Next'")
                    return True
            return False
        except Exception:
            return False

    def _fill_visible_fields(self, page: "Page", profile: "CandidateProfile") -> int:
        """Fill all visible form fields on the current step."""
        filled = 0

        for lever_field, profile_attr in self.FIELD_MAP.items():
            if lever_field in ("resume", "cover"):
                continue  # handled separately

            value = self._get_profile_value(profile, profile_attr)
            if not value:
                continue

            for sel_template in self.TEXT_FIELD_SELECTORS:
                selector = sel_template.format(field=lever_field)
                try:
                    el = page.query_selector(selector)
                    if el and el.is_visible():
                        el.click()
                        el.fill("")
                        el.fill(str(value))
                        filled += 1
                        break
                except Exception:
                    continue

        # Handle dropdowns (Lever uses custom select)
        try:
            selects = page.query_selector_all("select")
            for sel_el in selects:
                name = sel_el.get_attribute("name") or ""
                if "country" in name.lower():
                    try:
                        sel_el.select_option("United States")
                        filled += 1
                    except Exception:
                        pass
        except Exception:
            pass

        return filled

    def _get_profile_value(self, profile: "CandidateProfile", attr) -> str:
        """Extract a value from the profile."""
        if isinstance(attr, tuple):
            _, transformer = attr
            return str(transformer(profile)) if transformer else ""
        return str(getattr(profile, attr, "") or "")
