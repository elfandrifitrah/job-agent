"""
Career Page Scanner — scrapes company career pages directly for job listings.

Uses Firecrawl (free tier) to scrape career page URLs, then parses job listings
using the appropriate ATS adapter (greenhouse, lever, workday) or generic HTML parsing.

Pipeline:
  1. Load target_companies.yaml
  2. For each company, scrape their career page via Firecrawl
  3. Route to the correct ATS adapter for structured parsing
  4. Filter by target roles (e.g. "Product Manager")
  5. Deduplicate and store alongside live_jobs
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from backend.config import settings
from backend.models.profile import JobPosting, SeniorityLevel

logger = logging.getLogger(__name__)

COMPANIES_FILE = Path(__file__).parent.parent / "data" / "target_companies.yaml"


@dataclass
class CompanyTarget:
    name: str
    career_url: str
    ats: str = "generic"
    roles: list[str] = field(default_factory=lambda: ["Product Manager"])


def load_target_companies() -> list[CompanyTarget]:
    """Load the target company list from YAML."""
    if not COMPANIES_FILE.exists():
        logger.warning("Target companies file not found: %s", COMPANIES_FILE)
        return []
    with open(COMPANIES_FILE) as f:
        data = yaml.safe_load(f)
    companies = []
    for c in data.get("companies", []):
        companies.append(CompanyTarget(
            name=c["name"],
            career_url=c["career_url"],
            ats=c.get("ats", "generic"),
            roles=c.get("roles", ["Product Manager"]),
        ))
    return companies


def _fetch_html_via_firecrawl(url: str, api_key: str) -> str | None:
    """Fetch a URL via Firecrawl scrape API and return the HTML content."""
    import httpx

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "url": url,
        "formats": ["html", "markdown"],
        "onlyMainContent": True,
    }

    try:
        resp = httpx.post(
            "https://api.firecrawl.dev/v1/scrape",
            json=payload,
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            logger.warning("Firecrawl scrape failed for %s: %s", url, data.get("error", "unknown"))
            return None
        html = data.get("data", {}).get("html", "")
        if not html:
            logger.warning("Firecrawl returned empty HTML for %s", url)
            return None
        return html
    except Exception as e:
        logger.warning("Firecrawl error for %s: %s", url, e)
        return None


def _normalise_job(
    title: str,
    company: str,
    description: str,
    url: str = "",
    location: str = "",
    remote: bool = False,
    salary: str | None = None,
    source: str = "career_page",
) -> JobPosting:
    """Create a normalised JobPosting with deterministic ID."""
    raw = f"{company}|{title}|{url}"
    job_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

    text = f"{title} {description}".lower()
    if re.search(r"\b(principal|staff|architect|director|head of)\b", text):
        seniority = SeniorityLevel.PRINCIPAL
    elif re.search(r"\bsenior|sr\.?\b", text):
        seniority = SeniorityLevel.SENIOR
    elif re.search(r"\b(mid(-level)?|intermediate)\b", text):
        seniority = SeniorityLevel.MID
    elif re.search(r"\bjunior|jr\.?\b", text):
        seniority = SeniorityLevel.JUNIOR
    elif re.search(r"\b(entry|graduate|intern)\b", text):
        seniority = SeniorityLevel.ENTRY
    else:
        seniority = SeniorityLevel.UNKNOWN

    return JobPosting(
        id=job_id,
        title=title.strip(),
        company=company.strip(),
        location=location.strip(),
        description=description.strip()[:3000] if description else "",
        url=url.strip(),
        source="career_pages",
        salary_range=salary,
        remote=remote,
        seniority=seniority,
    )


def _parse_greenhouse_jobs(html: str, company: CompanyTarget) -> list[JobPosting]:
    """Parse Greenhouse-hosted career page HTML for job listings.

    Greenhouse boards use a predictable structure:
    - Each job opening is in an <li> with class "opening"
    - Title in <a class="opening-link"> or <h4> with link
    - Location in <span class="location">
    - Department in <span class="department"> or <p class="metadata">
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobPosting] = []
    seen_urls: set[str] = set()

    # Try multiple Greenhouse board selectors
    opening_selectors = [
        "li.opening",
        "div.opening",
        "a.opening-link",
        "div[class*=opening]",
        "tr[data-openings]",
    ]

    openings = []
    for sel in opening_selectors:
        openings = soup.select(sel)
        if openings:
            break

    if not openings:
        # Fallback: find all links containing common job title patterns
        all_links = soup.find_all("a", href=True)
        pm_pattern = re.compile(r"(product manager|product lead|product director|pm)", re.IGNORECASE)
        for link in all_links:
            text = link.get_text(strip=True)
            if pm_pattern.search(text) and link.get("href"):
                jobs.append(_normalise_job(
                    title=text,
                    company=company.name,
                    url=link["href"] if link["href"].startswith("http") else f"https://boards.greenhouse.io{link['href']}",
                    location="Remote",
                    remote=True,
                    source="career_pages",
                ))
        logger.info("CareerPages [%s]: %d PM jobs via fallback link scan", company.name, len(jobs))
        return jobs

    for opening in openings:
        try:
            # Extract title
            title_el = opening.select_one("a.opening-link, h4 a, .job-title a, .title a")
            if not title_el:
                title_el = opening.find("a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")

            # Filter by target roles
            role_match = any(r.lower() in title.lower() for r in company.roles)
            if not role_match:
                continue

            # Build URL
            if href and not href.startswith("http"):
                href = f"https://boards.greenhouse.io{href}" if href.startswith("/") else href

            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Location
            loc_el = opening.select_one(".location, span.location, .job-location, [class*=location]")
            location = loc_el.get_text(strip=True) if loc_el else "Remote"

            # Department
            dept_el = opening.select_one(".department, .metadata, .department-label")
            description = f"Department: {dept_el.get_text(strip=True)}" if dept_el else ""

            remote = "remote" in location.lower()

            jobs.append(_normalise_job(
                title=title,
                company=company.name,
                description=description,
                url=href,
                location=location,
                remote=remote,
                source="career_pages",
            ))
        except Exception as e:
            logger.debug("Error parsing Greenhouse job card for %s: %s", company.name, e)
            continue

    logger.info("CareerPages [%s]: %d PM jobs from Greenhouse", company.name, len(jobs))
    return jobs


def _parse_lever_jobs(html: str, company: CompanyTarget) -> list[JobPosting]:
    """Parse Lever-hosted career page HTML for job listings.

    Lever boards use:
    - A list with class "postings-group" containing "posting" items
    - Each posting has a title in <a class="posting-title"> or <h5> with link
    - Categories/departments in .posting-categories
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobPosting] = []
    seen_urls: set[str] = set()

    postings = soup.select("div.posting, a.posting-title, div[class*=posting]")
    if not postings:
        # Fallback to all links with PM patterns
        all_links = soup.find_all("a", href=True)
        pm_pattern = re.compile(r"(product manager|product lead|pm)", re.IGNORECASE)
        for link in all_links:
            text = link.get_text(strip=True)
            if pm_pattern.search(text) and text not in seen_urls:
                seen_urls.add(text)
                jobs.append(_normalise_job(
                    title=text,
                    company=company.name,
                    url=link["href"] if link["href"].startswith("http") else f"https://jobs.lever.co{link['href']}",
                    location="Remote",
                    remote=True,
                    source="career_pages",
                ))
        logger.info("CareerPages [%s]: %d PM jobs via Lever fallback", company.name, len(jobs))
        return jobs

    for posting in postings:
        try:
            title_el = posting if posting.name == "a" else (
                posting.select_one("a.posting-title, h5 a, a[class*=title]") or posting.find("a")
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")

            if not href:
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)

            role_match = any(r.lower() in title.lower() for r in company.roles)
            if not role_match:
                continue

            if href.startswith("/"):
                href = f"https://jobs.lever.co{href}"

            loc_el = posting.select_one(".location, span.location, [class*=location]")
            location = loc_el.get_text(strip=True) if loc_el else "Remote"

            remote = "remote" in location.lower()

            # Get categories/department
            cat_el = posting.select_one(".posting-categories, .categories, [class*=category]")
            description = f"Department: {cat_el.get_text(strip=True)}" if cat_el else ""

            jobs.append(_normalise_job(
                title=title,
                company=company.name,
                description=description,
                url=href,
                location=location,
                remote=remote,
                source="career_pages",
            ))
        except Exception as e:
            logger.debug("Error parsing Lever job for %s: %s", company.name, e)
            continue

    logger.info("CareerPages [%s]: %d PM jobs via Lever", company.name, len(jobs))
    return jobs


def _parse_workday_jobs(html: str, company: CompanyTarget) -> list[JobPosting]:
    """Parse Workday-hosted career page HTML for job listings.

    Workday is notoriously varied, so we use a generic link scan with
    role filtering.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobPosting] = []
    seen_urls: set[str] = set()

    all_links = soup.find_all("a", href=True)
    pm_pattern = re.compile(r"(product manager|product lead|product owner|pm)", re.IGNORECASE)

    for link in all_links:
        try:
            text = link.get_text(strip=True)
            href = link.get("href", "")
            if not text or not href:
                continue
            role_match = any(r.lower() in text.lower() for r in company.roles)
            if not role_match:
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)

            if href.startswith("/"):
                href = f"https://{company.name.lower().replace(' ', '')}.wd5.myworkdayjobs.com{href}"

            jobs.append(_normalise_job(
                title=text,
                company=company.name,
                url=href,
                location="Remote",
                remote=True,
                source="career_pages",
            ))
        except Exception as e:
            logger.debug("Error parsing Workday link for %s: %s", company.name, e)
            continue

    logger.info("CareerPages [%s]: %d PM jobs via Workday", company.name, len(jobs))
    return jobs


def _parse_generic_jobs(html: str, company: CompanyTarget) -> list[JobPosting]:
    """Parse a generic career page for job listings.

    Uses regex and BeautifulSoup to find job links containing role keywords.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobPosting] = []
    seen_urls: set[str] = set()

    # Find all links with text containing role keywords
    all_links = soup.find_all("a", href=True)
    role_pattern = re.compile(
        r"(product manager|product lead|product director|product owner|pm)",
        re.IGNORECASE,
    )

    for link in all_links:
        try:
            text = link.get_text(strip=True)
            href = link.get("href", "")
            if not text or not href:
                continue
            if not role_pattern.search(text):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Make relative URLs absolute
            if href.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(company.career_url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"

            jobs.append(_normalise_job(
                title=text,
                company=company.name,
                url=href,
                location="Remote",
                remote=True,
                source="career_pages",
            ))
        except Exception as e:
            logger.debug("Error parsing generic job for %s: %s", company.name, e)
            continue

    logger.info("CareerPages [%s]: %d PM jobs via generic scan", company.name, len(jobs))
    return jobs


ATS_PARSERS = {
    "greenhouse": _parse_greenhouse_jobs,
    "lever": _parse_lever_jobs,
    "workday": _parse_workday_jobs,
    "generic": _parse_generic_jobs,
}


def scan_career_page(company: CompanyTarget) -> list[JobPosting]:
    """Scan a single company's career page and return matching job listings."""
    api_key = settings.firecrawl_api_key
    if not api_key:
        logger.warning("Firecrawl API key not configured — cannot scan career pages")
        return []

    logger.info("CareerPages: scanning %s (%s) via %s", company.name, company.career_url, company.ats)

    html = _fetch_html_via_firecrawl(company.career_url, api_key)
    if not html:
        logger.warning("CareerPages: no HTML for %s", company.name)
        return []

    parser = ATS_PARSERS.get(company.ats, _parse_generic_jobs)
    try:
        jobs = parser(html, company)
    except Exception as e:
        logger.warning("CareerPages: parser error for %s: %s", company.name, e)
        return []

    return jobs


async def scan_all_career_pages(
    role_keyword: str = "Product Manager",
    max_companies: int = 10,
) -> list[dict[str, Any]]:
    """Scan all target company career pages and return job listings.

    Args:
        role_keyword: Only return jobs matching this role (default: Product Manager)
        max_companies: Max companies to scan per run (default: 10, to stay within Firecrawl free tier)

    Returns:
        List of job dicts ready for storage
    """
    companies = load_target_companies()
    if not companies:
        logger.warning("No target companies configured")
        return []

    all_jobs: list[JobPosting] = []
    seen_ids: set[str] = set()
    scanned_count = 0

    for company in companies:
        if scanned_count >= max_companies:
            logger.info("CareerPages: reached max_companies limit (%d)", max_companies)
            break

        jobs = scan_career_page(company)
        scanned_count += 1

        for job in jobs:
            # Filter by role keyword
            if role_keyword.lower() not in job.title.lower():
                continue
            if job.id not in seen_ids:
                seen_ids.add(job.id)
                all_jobs.append(job)

    logger.info("CareerPages: %d unique PM jobs from %d companies", len(all_jobs), scanned_count)
    return [j.model_dump(mode="json") for j in all_jobs]
