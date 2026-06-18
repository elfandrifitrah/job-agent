"""
Workday ATS Adapter — form filling for Workday-powered career portals.

Workday is notoriously difficult to automate because:
  - Heavy JavaScript-rendered forms with dynamic IDs
  - Uses Web Components / shadow DOM in some instances
  - Multi-step wizard with conditional sections
  - Requires answering screening questions (yes/no, select, text)
  - Different tenant configurations (custom fields)

Strategy:
  1. Navigate to the job posting page
  2. Click the "Apply" button (often in a floating footer)
  3. Step through multi-page wizard filling each section
  4. Detect and fill common Workday field patterns
  5. Handle screening questions as best-effort
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

from backend.services.ats_adapters import ATSAdapter

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from backend.models.profile import CandidateProfile

logger = logging.getLogger(__name__)


class WorkdayAdapter(ATSAdapter):
    """Adapter for Workday-powered career portals."""

    name = "workday"

    # Workday label keywords → profile attribute mapping
    LABEL_MAP = [
        (["first name", "given name"], "full_name", lambda p: p.full_name.split()[0] if p.full_name else ""),
        (["last name", "family name", "surname"], "full_name", lambda p: p.full_name.split()[-1] if p.full_name and len(p.full_name.split()) > 1 else ""),
        (["email"], "email", None),
        (["phone", "phone number", "mobile"], "phone", None),
        (["linkedin"], "linkedin_url", None),
        (["github", "git hub"], "github_url", None),
        (["website", "portfolio", "personal site"], "portfolio_url", None),
        (["location", "city"], ("location", lambda p: p.location or (p.preferred_locations[0] if p.preferred_locations else "")), None),
        (["current company", "current employer"], ("current_company", lambda p: p.experiences[0].company if p.experiences else ""), None),
        (["current title", "job title", "title"], ("current_title", lambda p: p.experiences[0].title if p.experiences else ""), None),
        (["years of experience", "work experience"], ("years_experience", lambda p: str(int(p.years_of_experience))), None),
    ]

    def detect(self, page: "Page") -> bool:
        """Check if the page is a Workday career portal."""
        try:
            url = page.url.lower()
            workday_domains = [
                "myworkdayjobs.com", "myworkday.com", "workday.com",
                "wd5.myworkdayjobs.com", "wd3.myworkdayjobs.com",
                "wd1.myworkdayjobs.com", "wd2.myworkdayjobs.com",
            ]
            if any(d in url for d in workday_domains):
                return True

            # Check for Workday-specific DOM patterns
            indicators = [
                page.query_selector("[data-automation-id]"),
                page.query_selector("[data-wd]"),
                page.query_selector(".workday-application-form"),
                page.query_selector("script[src*='workday']"),
            ]
            return any(bool(i) for i in indicators)
        except Exception:
            return False

    def fill_form(self, page: "Page", profile: "CandidateProfile", cv_path: str = "") -> bool:
        """Fill the Workday application form, stepping through the wizard."""
        filled = 0

        # 1. Click "Apply" / "Sign In" / apply button
        self._click_apply(page)

        # Wait for form to load
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # 2. Step through the wizard pages
        max_pages = 10
        stuck_count = 0

        for page_num in range(max_pages):
            if stuck_count >= 3:
                logger.info("Workday: stopping — stuck on page %d", page_num)
                break

            # Fill fields on current page
            page_filled = self._fill_current_page(page, profile)
            if page_filled > 0:
                filled += page_filled
                stuck_count = 0

            # Upload resume if we see a file input
            if cv_path:
                try:
                    file_input = page.query_selector("input[type=file]")
                    if file_input and file_input.is_visible():
                        file_input.set_input_files(cv_path)
                        logger.info("Workday: resume uploaded")
                        filled += 1
                except Exception as e:
                    logger.debug("Workday: file upload attempt failed: %s", e)

            # Try to advance to next page
            if not self._click_next(page):
                stuck_count += 1
                logger.debug("Workday: no 'Next' button found (page %d)", page_num + 1)
            else:
                stuck_count = 0
                # Wait for next page to load
                try:
                    page.wait_for_timeout(2000)
                except Exception:
                    pass

        self._fill_screening_questions(page, profile)
        return filled > 0

    def submit(self, page: "Page") -> bool:
        """Submit the Workday application — usually the last 'Submit' button."""
        submit_selectors = [
            "button[data-automation-id='submitButton']",
            "button:has-text('Submit')",
            "button:has-text('Submit Application')",
            "button[type=submit]",
            "[data-automation-id*=submit]",
            "button:has-text('Review and Submit')",
        ]
        for sel in submit_selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    logger.info("Workday: application submitted")
                    return True
            except Exception:
                continue
        return False

    def _click_apply(self, page: "Page") -> None:
        """Click the initial apply button (varies by tenant)."""
        apply_selectors = [
            "button:has-text('Apply')",
            "button:has-text('Apply Now')",
            "a:has-text('Apply')",
            "a:has-text('Apply Now')",
            "[data-automation-id='applyButton']",
            ".css-apply-button",
            "button:has-text('Sign In to Apply')",
            "button:has-text('Apply with Indeed')",
        ]
        for sel in apply_selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    logger.debug("Workday: clicked apply button")
                    return
            except Exception:
                continue

    def _click_next(self, page: "Page") -> bool:
        """Click the 'Next', 'Continue', or 'Review' button to advance."""
        next_selectors = [
            "button:has-text('Next')",
            "button:has-text('Continue')",
            "button:has-text('Review')",
            "button:has-text('Review and Submit')",
            "[data-automation-id='nextButton']",
            "[data-automation-id='continueButton']",
            "button:has-text('Save and Continue')",
            "button[aria-label='Next']",
        ]
        for sel in next_selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    logger.debug("Workday: clicked next button")
                    return True
            except Exception:
                continue
        return False

    def _fill_current_page(self, page: "Page", profile: "CandidateProfile") -> int:
        """Fill visible form fields on the current wizard page."""
        filled = 0

        # Strategy 1: Find inputs by their associated label text
        try:
            labels = page.query_selector_all("label")
            for label in labels:
                label_text = label.inner_text().strip().lower()
                if not label_text or len(label_text) > 100:
                    continue

                # Find the associated input
                for_attr = label.get_attribute("for")
                if for_attr:
                    input_el = page.query_selector(f"#{for_attr}")
                else:
                    input_el = page.evaluate("""
                        (label) => {
                            const input = label.querySelector('input, textarea, select');
                            return input;
                        }
                    """, label)

                if not input_el:
                    continue

                value = self._match_label_to_value(label_text, profile)
                if value:
                    try:
                        tag = input_el.evaluate("el => el.tagName.toLowerCase()")
                        if tag == "select":
                            try:
                                input_el.select_option(value)
                            except Exception:
                                # Try partial text match
                                pass
                        elif tag == "textarea":
                            input_el.click()
                            input_el.fill("")
                            input_el.fill(value)
                        else:
                            input_type = (input_el.get_attribute("type") or "text").lower()
                            if input_type in ("text", "email", "tel", "url", "number"):
                                input_el.click()
                                input_el.fill("")
                                input_el.fill(value)
                        filled += 1
                    except Exception:
                        continue

        except Exception as e:
            logger.debug("Workday: label-based filling error: %s", e)

        # Strategy 2: Find inputs by placeholder text
        if filled < 5:
            try:
                inputs = page.query_selector_all("input:not([type=hidden]):not([type=submit]):not([type=file])")
                for input_el in inputs:
                    if not input_el.is_visible():
                        continue
                    placeholder = (input_el.get_attribute("placeholder") or "").lower()
                    if not placeholder:
                        continue
                    value = self._match_label_to_value(placeholder, profile)
                    if value:
                        try:
                            input_el.click()
                            input_el.fill("")
                            input_el.fill(value)
                            filled += 1
                        except Exception:
                            continue
            except Exception:
                pass

        return filled

    def _fill_screening_questions(self, page: "Page", profile: "CandidateProfile") -> int:
        """Attempt to handle Workday screening questions (yes/no, select)."""
        filled = 0

        try:
            # Yes/No radio questions
            radio_groups = page.query_selector_all("input[type=radio]")
            seen_names = set()
            for radio in radio_groups:
                name = radio.get_attribute("name") or ""
                if name in seen_names:
                    continue
                seen_names.add(name)

                # Find the parent question text
                parent = radio.evaluate("""
                    (el) => {
                        const container = el.closest('fieldset, div[role=group], .css-question');
                        return container?.querySelector('legend, label, span[data-automation-id]')?.innerText || '';
                    }
                """)

                parent_lower = parent.lower()
                value = "No"  # Default: answer "No" to decline

                # If they ask about authorisation / sponsorship, answer truthfully
                # Defaulting to "Yes" for authorised, "No" for visa sponsorship
                if "sponsor" in parent_lower or "visa" in parent_lower:
                    value = "No"
                elif "authorized" in parent_lower or "authorised" in parent_lower or "work legally" in parent_lower:
                    value = "Yes"
                elif "disability" in parent_lower or "veteran" in parent_lower or "eeo" in parent_lower or "equal opportunity" in parent_lower:
                    value = "No"  # Decline to answer

                # Click the radio with the matching value
                radios = page.query_selector_all(f"input[name=\"{name}\"]")
                for r in radios:
                    r_value = r.get_attribute("value") or ""
                    if r_value.lower() == value.lower():
                        r.check()
                        filled += 1
                        break
        except Exception as e:
            logger.debug("Workday: screening questions error: %s", e)

        # Handle simple select dropdowns
        try:
            selects = page.query_selector_all("select")
            for sel in selects:
                if not sel.is_visible():
                    continue
                try:
                    options = sel.query_selector_all("option")
                    if len(options) > 1:
                        # Pick the first non-empty option (skip "-- select --")
                        for opt in options:
                            opt_text = opt.inner_text().strip()
                            if opt_text and "select" not in opt_text.lower():
                                sel.select_option(value=opt.get_attribute("value") or "")
                                filled += 1
                                break
                except Exception:
                    continue
        except Exception:
            pass

        return filled

    def _match_label_to_value(self, label_text: str, profile: "CandidateProfile") -> str:
        """Match a field label to a profile value."""
        for keywords, attr, transformer in self.LABEL_MAP:
            if any(kw in label_text for kw in keywords):
                # If a transformer exists, apply it to derive a value
                if transformer:
                    val = transformer(profile)
                elif isinstance(attr, tuple):
                    field_name, extractor = attr
                    val = str(extractor(profile)) if extractor else ""
                elif attr == "cover_letter_text":
                    return ""
                else:
                    val = str(getattr(profile, attr, "") or "")

                if not val or val == "None":
                    return ""
                return val
        return ""
