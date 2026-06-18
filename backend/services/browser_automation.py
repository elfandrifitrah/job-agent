"""
Browser Automation Engine — Playwright-powered form filling for job applications.

Capabilities:
  - Launch headless/headed Chromium browser
  - Navigate to job application URLs
  - Auto-detect form fields (input, select, textarea, file upload)
  - Smart field filling using candidate profile data
  - File upload (CV, cover letter)
  - ATS adapter detection and delegation
  - CAPTCHA detection with human-in-the-loop fallback
  - Screenshot capture for debugging and human review

Architecture:
  BrowserAutomation (orchestrator)
    ├── FormDetector (field detection + mapping)
    ├── FormFiller (profile → form field mapping)
    ├── FileUploader (CV + cover letter upload)
    ├── CaptchaDetector (CAPTCHA detection)
    └── HumanLoop (interactive fallback)
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from backend.config import settings
from backend.models.profile import CandidateProfile

logger = logging.getLogger(__name__)


# ─── Types ──────────────────────────────────────────────────────────────────


class FieldType(str, Enum):
    """HTML form field types that the engine can handle."""
    TEXT = "text"
    EMAIL = "email"
    PHONE = "tel"
    URL = "url"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    FILE = "file"
    DATE = "date"
    PASSWORD = "password"
    UNKNOWN = "unknown"


@dataclass
class FormField:
    """Metadata about a detected form field."""
    selector: str                    # CSS selector for this field
    name: str = ""                   # name attribute
    id: str = ""                     # id attribute
    label: str = ""                  # Visible label text (if found)
    placeholder: str = ""            # placeholder text
    field_type: FieldType = FieldType.UNKNOWN
    required: bool = False
    autocomplete: str = ""           # autocomplete attribute hint
    aria_label: str = ""             # aria-label attribute
    class_list: list[str] = field(default_factory=list)

    @property
    def hints(self) -> list[str]:
        """All text hints combined for matching."""
        hints = []
        for val in [self.label, self.placeholder, self.name, self.id, self.aria_label, self.autocomplete]:
            if val:
                hints.append(val.lower())
        return hints


@dataclass
class FormPage:
    """Snapshot of a detected form on a page."""
    url: str = ""
    fields: list[FormField] = field(default_factory=list)
    has_file_upload: bool = False
    has_captcha: bool = False
    submit_selectors: list[str] = field(default_factory=list)
    detected_ats: str = "unknown"


@dataclass
class ApplicationResult:
    """Result of an automated application attempt."""
    success: bool = False
    status: str = "pending"           # pending, submitted, captcha_blocked, error, human_intervention
    url: str = ""
    ats: str = "unknown"
    fields_filled: int = 0
    total_fields: int = 0
    file_uploaded: bool = False
    captcha_detected: bool = False
    error_message: str = ""
    screenshot_path: Optional[str] = None
    submitted_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ─── Form Detection ─────────────────────────────────────────────────────────


class FormDetector:
    """Detects and analyses form fields on a page."""

    # CSS selectors mapping field types to detection patterns
    FIELD_SELECTORS = {
        "input": "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=image]):not([type=reset])",
        "textarea": "textarea",
        "select": "select",
        "file": "input[type=file]",
        "checkbox": "input[type=checkbox]",
        "radio": "input[type=radio]",
        "submit": "button[type=submit], input[type=submit], button:has-text('Submit'), button:has-text('Apply'), button:has-text('Send'), a:has-text('Submit application')",
    }

    # Autocomplete attribute mapping: autocomplete value → profile field
    AUTOCOMPLETE_MAP = {
        "name": "full_name",
        "given-name": "first_name",
        "family-name": "last_name",
        "email": "email",
        "tel": "phone",
        "tel-national": "phone",
        "street-address": "address",
        "address-line1": "address",
        "address-level2": "city",
        "address-level1": "state",
        "postal-code": "zip",
        "country-name": "country",
        "organization": "company",
        "job-title": "title",
        "url": "portfolio_url",
        "github": "github_url",
        "linkedin": "linkedin_url",
    }

    def detect_fields(self, page) -> list[FormField]:
        """Scan the page and return all detected form fields."""
        fields: list[FormField] = []

        try:
            # Detect input fields
            inputs = page.query_selector_all(self.FIELD_SELECTORS["input"])
            for el in inputs:
                field = self._parse_input_field(page, el)
                if field:
                    fields.append(field)
        except Exception as e:
            logger.debug("Error detecting input fields: %s", e)

        try:
            textareas = page.query_selector_all(self.FIELD_SELECTORS["textarea"])
            for el in textareas:
                field = self._parse_textarea(page, el)
                if field:
                    fields.append(field)
        except Exception as e:
            logger.debug("Error detecting textareas: %s", e)

        try:
            selects = page.query_selector_all(self.FIELD_SELECTORS["select"])
            for el in selects:
                field = self._parse_select(page, el)
                if field:
                    fields.append(field)
        except Exception as e:
            logger.debug("Error detecting select fields: %s", e)

        return fields

    def detect_file_upload(self, page) -> bool:
        """Check if the page has a file upload input."""
        try:
            return bool(page.query_selector(self.FIELD_SELECTORS["file"]))
        except Exception:
            return False

    def detect_submit_buttons(self, page) -> list[str]:
        """Find submit/apply buttons on the page."""
        selectors = []
        try:
            buttons = page.query_selector_all(self.FIELD_SELECTORS["submit"])
            for btn in buttons:
                try:
                    sel = self._build_selector(btn)
                    if sel:
                        selectors.append(sel)
                except Exception:
                    continue
        except Exception:
            pass
        return selectors

    def _parse_input_field(self, page, el) -> Optional[FormField]:
        """Extract metadata from an input element."""
        try:
            type_attr = (el.get_attribute("type") or "text").lower()
            field_type = self._map_type(type_attr)

            return FormField(
                selector=self._build_selector(el),
                name=el.get_attribute("name") or "",
                id=el.get_attribute("id") or "",
                label=self._find_label(el),
                placeholder=el.get_attribute("placeholder") or "",
                field_type=field_type,
                required=el.get_attribute("required") is not None or el.get_attribute("aria-required") == "true",
                autocomplete=el.get_attribute("autocomplete") or "",
                aria_label=el.get_attribute("aria-label") or "",
                class_list=el.get_attribute("class") or "",
            )
        except Exception:
            return None

    def _parse_textarea(self, page, el) -> Optional[FormField]:
        """Extract metadata from a textarea element."""
        try:
            return FormField(
                selector=self._build_selector(el),
                name=el.get_attribute("name") or "",
                id=el.get_attribute("id") or "",
                label=self._find_label(el),
                placeholder=el.get_attribute("placeholder") or "",
                field_type=FieldType.TEXTAREA,
                required=el.get_attribute("required") is not None,
                aria_label=el.get_attribute("aria-label") or "",
                class_list=el.get_attribute("class") or "",
            )
        except Exception:
            return None

    def _parse_select(self, page, el) -> Optional[FormField]:
        """Extract metadata from a select element."""
        try:
            return FormField(
                selector=self._build_selector(el),
                name=el.get_attribute("name") or "",
                id=el.get_attribute("id") or "",
                label=self._find_label(el),
                field_type=FieldType.SELECT,
                required=el.get_attribute("required") is not None,
                aria_label=el.get_attribute("aria-label") or "",
                class_list=el.get_attribute("class") or "",
            )
        except Exception:
            return None

    def _find_label(self, el) -> str:
        """Find the associated label for a form element."""
        try:
            # Check aria-label
            aria = el.get_attribute("aria-label")
            if aria:
                return aria

            # Check for a wrapping label
            parent = el.evaluate("el => el.closest('label')?.innerText || ''")
            if parent:
                return parent.strip()

            # Check for preceding label using 'for' attribute
            el_id = el.get_attribute("id")
            if el_id:
                label_text = el.evaluate(
                    f"document.querySelector('label[for=\"{el_id}\"]')?.innerText || ''"
                )
                if label_text:
                    return label_text.strip()

            # Check placeholder
            placeholder = el.get_attribute("placeholder")
            if placeholder:
                return placeholder
        except Exception:
            pass
        return ""

    def _build_selector(self, el) -> str:
        """Build a unique CSS selector for an element."""
        try:
            # Prefer ID
            el_id = el.get_attribute("id")
            if el_id and not re.match(r"^\d", el_id):
                return f"#{el_id}"

            # Use name attribute
            name = el.get_attribute("name")
            if name:
                tag = el.evaluate("el => el.tagName.toLowerCase()")
                return f"{tag}[name=\"{name}\"]"

            # Build from class + type + nth-child
            tag = el.evaluate("el => el.tagName.toLowerCase()")
            classes = (el.get_attribute("class") or "").strip()
            if classes:
                cls_sel = ".".join(classes.split()[:2])
                return f"{tag}.{cls_sel}"

            return tag
        except Exception:
            return "input"

    @staticmethod
    def _map_type(type_str: str) -> FieldType:
        mapping = {
            "text": FieldType.TEXT,
            "email": FieldType.EMAIL,
            "tel": FieldType.PHONE,
            "url": FieldType.URL,
            "number": FieldType.TEXT,
            "date": FieldType.DATE,
            "file": FieldType.FILE,
            "checkbox": FieldType.CHECKBOX,
            "radio": FieldType.RADIO,
            "password": FieldType.PASSWORD,
        }
        return mapping.get(type_str, FieldType.UNKNOWN)


# ─── Form Filling ───────────────────────────────────────────────────────────


class FormFiller:
    """Maps candidate profile data to detected form fields and fills them."""

    # Keyword → profile attribute mapping for field matching
    FIELD_MAP: list[tuple[list[str], str, Optional[callable]]] = [
        (["first name", "firstname", "given name", "fname"], "full_name", lambda p: p.full_name.split()[0] if p.full_name else ""),
        (["last name", "lastname", "family name", "surname", "lname"], "full_name", lambda p: p.full_name.split()[-1] if p.full_name and len(p.full_name.split()) > 1 else ""),
        (["full name", "name", "candidate name", "applicant name", "your name"], "full_name", None),
        (["email", "e-mail", "email address"], "email", None),
        (["phone", "telephone", "phone number", "tel", "mobile", "cell"], "phone", None),
        (["linkedin", "linkedin url", "linkedin profile"], "linkedin_url", None),
        (["github", "github url", "github profile"], "github_url", None),
        (["portfolio", "website", "personal website", "portfolio url", "web"], "portfolio_url", None),
        (["current company", "company", "employer", "organization"], "current_company", lambda p: p.experiences[0].company if p.experiences else ""),
        (["current title", "current role", "job title", "title", "position"], "current_title", lambda p: p.experiences[0].title if p.experiences else ""),
        (["location", "city", "current location"], "location", None),
        (["cover letter", "coverletter", "message", "additional info", "notes", "why you"], "cover_letter_text", None),
        (["education", "school", "university", "college"], "education_text", lambda p: p.education[0].institution if p.education else ""),
        (["years experience", "years of experience", "experience years"], "years_experience", None),
    ]

    def __init__(self, profile: CandidateProfile, cover_letter_text: str = ""):
        self.profile = profile
        self.cover_letter_text = cover_letter_text

    def fill_fields(self, page, fields: list[FormField]) -> int:
        """Fill detected form fields with profile data. Returns count of filled fields."""
        filled = 0

        for field in fields:
            value = self._match_value(field)
            if value is None or value == "":
                continue

            try:
                if field.field_type == FieldType.SELECT:
                    self._fill_select(page, field.selector, value)
                elif field.field_type == FieldType.CHECKBOX:
                    self._fill_checkbox(page, field.selector, value)
                elif field.field_type == FieldType.TEXTAREA:
                    self._fill_text(page, field.selector, value)
                else:
                    self._fill_text(page, field.selector, value)
                filled += 1
                logger.debug("Filled field '%s' (%s) with '%s'", field.label or field.name, field.selector, str(value)[:50])
            except Exception as e:
                logger.debug("Failed to fill field '%s': %s", field.name, e)
                continue

        return filled

    def upload_file(self, page, file_path: str) -> bool:
        """Upload a file to a file input field."""
        try:
            file_input = page.query_selector("input[type=file]")
            if file_input:
                file_input.set_input_files(file_path)
                logger.info("File uploaded: %s", file_path)
                return True
        except Exception as e:
            logger.warning("File upload failed: %s", e)
        return False

    def _match_value(self, field: FormField) -> Any:
        """Match a form field to a profile attribute and return the value."""
        hints = field.hints
        if not hints:
            return None

        hints_str = " ".join(hints)

        for keywords, attr, transformer in self.FIELD_MAP:
            if any(kw in hints_str for kw in keywords):
                # If a transformer exists, use it to derive the value from the profile
                if transformer:
                    value = transformer(self.profile)
                else:
                    # Direct attribute lookup
                    value = getattr(self.profile, attr, None)
                    if callable(value):
                        value = value()

                # Handle special "cover_letter_text" → stored CL
                if attr == "cover_letter_text" and not value:
                    value = self.cover_letter_text

                # Handle first/last name extraction from full_name
                if attr == "full_name" and transformer is None and value:
                    # Direct full_name field — use as-is
                    pass

                if value and attr in ("github_url", "linkedin_url", "portfolio_url"):
                    # Some forms want just the handle, others the full URL
                    if "handle" in hints_str or "username" in hints_str:
                        value = value.rstrip("/").split("/")[-1]

                # Location hint (uses profile.location from transformer or direct)
                if attr == "location" and not value:
                    value = self.profile.location or (self.profile.preferred_locations[0] if self.profile.preferred_locations else "")

                # Years experience
                if attr == "years_experience" and not value:
                    value = str(int(self.profile.years_of_experience))

                return str(value) if value else None

        return None

    def _fill_text(self, page, selector: str, value: str) -> None:
        """Type text into a field, clearing existing content first."""
        el = page.query_selector(selector)
        if el:
            el.click()
            el.fill("")
            page.keyboard.press("Control+a")
            el.fill(str(value))

    def _fill_select(self, page, selector: str, value: str) -> None:
        """Select an option from a dropdown."""
        el = page.query_selector(selector)
        if el:
            try:
                el.select_option(value)
            except Exception:
                # Try partial text match
                options = el.query_selector_all("option")
                for opt in options:
                    opt_text = opt.inner_text().lower()
                    if value.lower() in opt_text:
                        el.select_option(value=opt.get_attribute("value") or "")
                        break

    def _fill_checkbox(self, page, selector: str, value: Any) -> None:
        """Check or uncheck a checkbox based on truthy/falsy value."""
        el = page.query_selector(selector)
        if el:
            is_checked = el.is_checked()
            should_check = bool(value) and str(value).lower() not in ("no", "false", "0")
            if should_check and not is_checked:
                el.check()
            elif not should_check and is_checked:
                el.uncheck()


# ─── File Uploader ──────────────────────────────────────────────────────────


class FileUploader:
    """Handles CV and cover letter file uploads."""

    def __init__(self, cv_path: str = "", cover_letter_path: str = ""):
        self.cv_path = Path(cv_path) if cv_path else None
        self.cover_letter_path = Path(cover_letter_path) if cover_letter_path else None

    def upload_all(self, page) -> bool:
        """Upload all available files. Returns True if any upload succeeded."""
        success = False
        file_inputs = page.query_selector_all("input[type=file]")

        if not file_inputs:
            return False

        for file_input in file_inputs:
            try:
                accept_attr = (file_input.get_attribute("accept") or "").lower()
                multiple = file_input.get_attribute("multiple") is not None

                paths = []
                if self.cv_path and self.cv_path.exists():
                    if any(ext in accept_attr for ext in [".pdf", ".doc", ".docx", ".txt"]) or not accept_attr:
                        paths.append(str(self.cv_path))

                if multiple and self.cover_letter_path and self.cover_letter_path.exists():
                    if any(ext in accept_attr for ext in [".pdf", ".doc", ".txt"]) or not accept_attr:
                        paths.append(str(self.cover_letter_path))

                if paths:
                    file_input.set_input_files(paths)
                    success = True
                    logger.info("Uploaded %d file(s) to %s", len(paths), file_input)
            except Exception as e:
                logger.warning("File upload failed for input: %s", e)
                continue

        return success


# ─── Browser Automation Orchestrator ────────────────────────────────────────


class BrowserAutomation:
    """
    Main orchestrator for browser-based job application automation.

    Handles the full pipeline:
      1. Launch browser
      2. Navigate to application URL
      3. Detect form fields
      4. Detect ATS type and use adapter
      5. Fill form fields from profile
      6. Upload files (CV, cover letter)
      7. Detect CAPTCHAs
      8. Submit or pause for human review
    """

    def __init__(
        self,
        profile: CandidateProfile,
        cv_path: str = "",
        cover_letter_path: str = "",
        headless: bool = True,
        human_review: bool = True,
        screenshots_dir: str = "./data/screenshots",
    ):
        self.profile = profile
        self.cv_path = cv_path
        self.cover_letter_path = cover_letter_path
        self.headless = headless
        self.human_review = human_review
        self.screenshots_dir = Path(screenshots_dir)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        self.form_detector = FormDetector()
        self.form_filler = FormFiller(profile, cover_letter_path)
        self.file_uploader = FileUploader(cv_path, cover_letter_path)

        # Lazy imports
        self._captcha_detector = None
        self._human_loop = None

        # Browser state
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None

    @property
    def captcha_detector(self):
        if self._captcha_detector is None:
            from backend.services.captcha_detector import CaptchaDetector
            self._captcha_detector = CaptchaDetector()
        return self._captcha_detector

    @property
    def human_loop(self):
        if self._human_loop is None:
            from backend.services.human_loop import HumanLoop
            self._human_loop = HumanLoop(profile=self.profile)
        return self._human_loop

    # ─── Browser lifecycle ──────────────────────────────────────────────────

    def launch(self) -> None:
        """Launch a Chromium browser instance."""
        try:
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            self._context = self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
                timezone_id="America/New_York",
            )
            # Suppress webdriver detection
            self._context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            self._page = self._context.new_page()
            logger.info("Browser launched (headless=%s)", self.headless)
        except Exception as e:
            logger.error("Failed to launch browser: %s", e)
            raise

    def close(self) -> None:
        """Close the browser and clean up resources."""
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning("Error closing browser: %s", e)
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            logger.info("Browser closed")

    @property
    def page(self):
        """Get the current page (raises if not launched)."""
        if not self._page:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._page

    # ─── Navigation ─────────────────────────────────────────────────────────

    def navigate(self, url: str, wait_until: str = "networkidle") -> bool:
        """Navigate to a URL and wait for the page to load."""
        try:
            self.page.goto(url, wait_until=wait_until, timeout=30000)
            self._random_delay(1, 3)
            logger.info("Navigated to: %s", url)
            return True
        except Exception as e:
            logger.warning("Navigation failed: %s", e)
            return False

    def _random_delay(self, min_s: float = 0.5, max_s: float = 2.0) -> None:
        """Randomised delay to appear more human-like."""
        time.sleep(random.uniform(min_s, max_s))

    # ─── Core application flow ──────────────────────────────────────────────

    def apply(
        self,
        url: str,
        use_ats_adapter: bool = True,
    ) -> ApplicationResult:
        """
        Apply to a job at the given URL.

        Args:
            url: The job application page URL.
            use_ats_adapter: If True, try to use ATS-specific adapter first.

        Returns:
            ApplicationResult with status and details.
        """
        result = ApplicationResult(url=url)

        # 1. Navigate to the application page
        if not self.navigate(url):
            result.status = "error"
            result.error_message = "Failed to navigate to URL"
            return result

        # 2. Take initial screenshot
        screenshot = self._take_screenshot("initial")
        result.screenshot_path = screenshot

        # 3. Detect ATS type
        if use_ats_adapter:
            from backend.services.ats_adapters import get_adapter
            adapter = get_adapter(url)
            result.ats = adapter.name
            logger.info("Detected ATS: %s", adapter.name)

            # Try to detect and use the ATS adapter
            try:
                if adapter.detect(self.page):
                    logger.info("Using ATS adapter: %s", adapter.name)
                    filled = adapter.fill_form(self.page, self.profile, self.cv_path)
                    result.fields_filled = filled
                    if filled > 0:
                        self._random_delay(1, 3)
                        if not self._check_captcha(result):
                            return result
                        submitted = adapter.submit(self.page)
                        result.success = submitted
                        result.status = "submitted" if submitted else "error"
                        if not submitted:
                            result.error_message = "ATS adapter submission failed"
                        return result
            except Exception as e:
                logger.warning("ATS adapter failed: %s — falling back to generic", e)

        # 4. Generic fallback: detect + fill fields manually
        return self._apply_generic(result)

    def _apply_generic(self, result: ApplicationResult) -> ApplicationResult:
        """Generic application flow — detect fields, fill, upload, submit."""
        # Detect form fields
        fields = self.form_detector.detect_fields(self.page)
        result.total_fields = len(fields)
        logger.info("Detected %d form fields", len(fields))

        if not fields:
            # Maybe the page needs a "Apply" button click first
            if not self._click_apply_button():
                result.status = "error"
                result.error_message = "No form fields detected on page"
                return result

            # Re-detect after clicking apply
            self._random_delay(2, 4)
            fields = self.form_detector.detect_fields(self.page)
            result.total_fields = len(fields)

            if not fields:
                result.status = "error"
                result.error_message = "No form fields detected after clicking apply"
                return result

        # Fill form fields
        filled = self.form_filler.fill_fields(self.page, fields)
        result.fields_filled = filled
        logger.info("Filled %d/%d fields", filled, len(fields))
        self._random_delay(1, 2)

        # Upload files
        result.file_uploaded = self.file_uploader.upload_all(self.page)
        self._random_delay(1, 2)

        # CAPTCHA check
        if not self._check_captcha(result):
            return result

        # Submit
        submitted = self._submit_form()
        result.success = submitted
        result.status = "submitted" if submitted else "error"

        if not submitted:
            result.error_message = "Submission failed — could not find or click submit button"

        return result

    def _click_apply_button(self) -> bool:
        """Click an 'Apply' or 'Apply Now' button on the page."""
        apply_selectors = [
            "button:has-text('Apply')",
            "a:has-text('Apply')",
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
            "[data-testid*=apply]",
            "[class*=apply]",
            "#apply-button",
            ".apply-button",
        ]
        for sel in apply_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    logger.info("Clicked apply button: %s", sel)
                    return True
            except Exception:
                continue
        return False

    def _check_captcha(self, result: ApplicationResult) -> bool:
        """Check for CAPTCHA and handle it. Returns True if we can proceed."""
        captcha_result = self.captcha_detector.detect(self.page)
        result.captcha_detected = captcha_result.detected

        if captcha_result.detected:
            logger.warning("CAPTCHA detected: %s (confidence: %.0f%%)",
                           captcha_result.captcha_type, captcha_result.confidence * 100)

            if self.human_review:
                # Pause for human intervention
                screenshot = self._take_screenshot("captcha_blocked")
                result.screenshot_path = screenshot

                from backend.services.human_loop import CaptchaHandler
                handler = CaptchaHandler(profile=self.profile)
                resolved = handler.handle_captcha(
                    page=self.page,
                    captcha_result=captcha_result,
                    screenshot_path=screenshot,
                )

                if resolved:
                    logger.info("CAPTCHA resolved by human")
                    return True
                else:
                    result.status = "captcha_blocked"
                    result.error_message = f"CAPTCHA ({captcha_result.captcha_type.value}) could not be resolved"
                    return False
            else:
                result.status = "captcha_blocked"
                result.error_message = f"CAPTCHA detected but human_review_mode is disabled"
                return False

        return True

    def _submit_form(self) -> bool:
        """Find and click the submit button."""
        submit_selectors = self.form_detector.detect_submit_buttons(self.page)
        submit_selectors.extend([
            "button[type=submit]",
            "input[type=submit]",
            "button:has-text('Submit')",
            "button:has-text('Submit Application')",
            "button:has-text('Send Application')",
            "button:has-text('Apply')",
            "[data-automation-id*=submit]",
        ])

        for sel in submit_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    self._random_delay(2, 4)
                    logger.info("Submit button clicked: %s", sel)
                    return True
            except Exception:
                continue
        return False

    def _take_screenshot(self, label: str = "") -> Optional[str]:
        """Capture a screenshot of the current page."""
        try:
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            label_slug = label.replace(" ", "_") if label else "page"
            path = str(self.screenshots_dir / f"{ts}_{label_slug}.png")
            self.page.screenshot(path=path, full_page=True)
            return path
        except Exception as e:
            logger.debug("Screenshot failed: %s", e)
            return None
