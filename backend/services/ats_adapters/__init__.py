"""
ATS Adapters — platform-specific form filling logic for major applicant tracking systems.

Each adapter implements the ATSAdapter protocol:
  - detect(page) -> bool           : whether the current page is this ATS
  - fill_form(page, profile, cv_path) -> bool : fill the application form
  - submit(page) -> bool           : submit the application

The get_adapter() function auto-detects the right adapter for a given URL.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from backend.models.profile import CandidateProfile

logger = logging.getLogger(__name__)


class ATSAdapter:
    """Base class for ATS-specific form adapters."""

    name: str = "generic"

    def detect(self, page: "Page") -> bool:
        """Return True if the current page is recognisable as this ATS."""
        return False

    def fill_form(self, page: "Page", profile: "CandidateProfile", cv_path: str = "") -> bool:
        """Fill the application form using data from the candidate profile."""
        raise NotImplementedError

    def submit(self, page: "Page") -> bool:
        """Click the submit button and confirm submission."""
        raise NotImplementedError


def get_adapter(url: str) -> ATSAdapter:
    """Auto-detect and return the appropriate ATS adapter for a URL."""
    url_lower = url.lower()

    if "greenhouse.io" in url_lower or "boards.greenhouse.io" in url_lower:
        from backend.services.ats_adapters.greenhouse import GreenhouseAdapter
        return GreenhouseAdapter()

    if "lever.co" in url_lower or "jobs.lever.co" in url_lower:
        from backend.services.ats_adapters.lever import LeverAdapter
        return LeverAdapter()

    if "myworkdayjobs.com" in url_lower or "workday.com" in url_lower or "wd5.myworkdayjobs.com" in url_lower:
        from backend.services.ats_adapters.workday import WorkdayAdapter
        return WorkdayAdapter()

    # Generic fallback — attempt heuristic field detection
    from backend.services.ats_adapters.generic import GenericAdapter
    return GenericAdapter()
