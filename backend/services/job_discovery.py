"""
Job Discovery — multi-source job search and aggregation.

Sources:
  - LinkedIn Jobs (Playwright-based scraping)
  - Indeed (Playwright-based scraping)
  - Adzuna API (free tier, no auth required for basic search)
  - Company career page crawler (generic)

Architecture:
  Each source implements the JobSource protocol. The JobDiscovery orchestrator
  queries all enabled sources, deduplicates, normalises, and stores results.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.models.profile import JobPosting, SeniorityLevel

logger = logging.getLogger(__name__)


@dataclass
class SearchParams:
    """Parameters for a job search query."""
    role: str = ""
    location: str = ""
    remote: bool = False
    max_results: int = 20
    days_old: int = 14


@dataclass
class SearchResult:
    """Aggregated results from all source adapters."""
    jobs: list[JobPosting] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    searched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Base adapter ───────────────────────────────────────────────────────────

class JobSource(ABC):
    """Abstract job source adapter."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Source identifier, e.g. 'linkedin', 'indeed'."""
        ...

    @abstractmethod
    def search(self, params: SearchParams) -> list[JobPosting]:
        """Search for jobs matching the given parameters."""
        ...

    def normalise(
        self,
        title: str,
        company: str,
        description: str,
        location: str = "",
        url: str = "",
        salary_range: Optional[str] = None,
        remote: bool = False,
        skills: Optional[list[str]] = None,
    ) -> JobPosting:
        """Create a normalised JobPosting with a deterministic ID."""
        raw = f"{company}|{title}|{url}"
        job_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

        seniority = self._detect_seniority(title, description)

        return JobPosting(
            id=job_id,
            title=title.strip(),
            company=company.strip(),
            location=location.strip(),
            description=description.strip()[:5000],
            url=url.strip(),
            source=self.name,
            salary_range=salary_range,
            remote=remote,
            skills_required=skills or [],
            seniority=seniority,
        )

    @staticmethod
    def _detect_seniority(title: str, description: str) -> SeniorityLevel:
        """Infer seniority from the job title and description."""
        text = f"{title} {description}".lower()
        if re.search(r"\b(principal|staff|architect)\b", text):
            return SeniorityLevel.PRINCIPAL
        if re.search(r"\bsenior\b", text):
            return SeniorityLevel.SENIOR
        if re.search(r"\b(mid(-level)?|intermediate)\b", text):
            return SeniorityLevel.MID
        if re.search(r"\bjunior\b", text):
            return SeniorityLevel.JUNIOR
        if re.search(r"\b(entry|graduate|intern)\b", text):
            return SeniorityLevel.ENTRY
        return SeniorityLevel.UNKNOWN


# ─── Adzuna API adapter ────────────────────────────────────────────────────

class AdzunaSource(JobSource):
    """Adzuna job search API — free tier, no OAuth, good coverage."""

    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    @property
    def name(self) -> str:
        return "adzuna"

    def search(self, params: SearchParams) -> list[JobPosting]:
        app_id = settings.adzuna_app_id
        api_key = settings.adzuna_api_key

        if not app_id or not api_key:
            logger.info("Adzuna not configured — skipping")
            return []

        country = "us"
        url = f"{self.BASE_URL}/{country}/search/1"

        query_parts = [params.role] if params.role else []
        if params.location:
            query_parts.append(params.location)

        query_params = {
            "app_id": app_id,
            "app_key": api_key,
            "results_per_page": min(params.max_results, 50),
            "sort_by": "relevance",
            "content-type": "application/json",
        }
        if query_parts:
            query_params["what"] = " ".join(query_parts)
        if params.location:
            query_params["where"] = params.location
        if params.remote:
            query_params["remote"] = "1"

        try:
            import httpx
            resp = httpx.get(url, params=query_params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            raw_jobs = data.get("results", [])

            jobs = []
            for raw in raw_jobs:
                title = raw.get("title", "")
                company = raw.get("company", {}).get("display_name", "Unknown")
                description = raw.get("description", "")
                location = raw.get("location", {}).get("display_name", "")
                redirect_url = raw.get("redirect_url", "")
                salary_min = raw.get("salary_min")
                salary_max = raw.get("salary_max")
                salary = f"${salary_min:,.0f} – ${salary_max:,.0f}" if salary_min and salary_max else None

                job = self.normalise(
                    title=title,
                    company=company,
                    description=description,
                    location=location,
                    url=redirect_url,
                    salary_range=salary,
                    remote="remote" in description.lower() or "remote" in title.lower(),
                )
                jobs.append(job)

            logger.info("Adzuna: found %d jobs for '%s'", len(jobs), params.role)
            return jobs

        except Exception as e:
            logger.warning("Adzuna search failed: %s", e)
            return []


# ─── Playwright-based scrapers ──────────────────────────────────────────────

class PlaywrightSource(JobSource):
    """Base class for Playwright-based job board scrapers."""

    def __init__(self, headless: bool = True):
        self.headless = headless

    def _get_page(self):
        """Lazy-import and launch a Playwright browser page."""
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=self.headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        return page, browser, p

    def _delay(self, min_s: float = 1.5, max_s: float = 3.5) -> None:
        """Randomised delay to avoid rate limiting."""
        time.sleep(random.uniform(min_s, max_s))


class LinkedInSource(PlaywrightSource):
    """LinkedIn Jobs scraper using Playwright."""

    @property
    def name(self) -> str:
        return "linkedin"

    def search(self, params: SearchParams) -> list[JobPosting]:
        if not settings.linkedin_email or not settings.linkedin_password:
            logger.info("LinkedIn credentials not configured — skipping")
            return []

        jobs: list[JobPosting] = []
        page = browser = playwright = None

        try:
            page, browser, playwright = self._get_page()

            # Login to LinkedIn
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            self._delay(2, 4)
            page.fill("#username", settings.linkedin_email)
            page.fill("#password", settings.linkedin_password)
            page.click("button[type=submit]")
            page.wait_for_load_state("networkidle")
            self._delay(3, 6)

            # Build search URL
            keywords = params.role.replace(" ", "%20")
            location = params.location.replace(" ", "%20") if params.location else ""
            search_url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={keywords}"
                f"&location={location}"
                f"&f_TPR=r{params.days_old * 86400}"  # past N days
            )
            if params.remote:
                search_url += "&f_WT=2"

            page.goto(search_url, wait_until="domcontentloaded")
            self._delay(3, 5)

            # Scroll to load more results
            for _ in range(5):
                page.evaluate("window.scrollBy(0, 800)")
                self._delay(0.5, 1)

            # Extract job cards
            cards = page.query_selector_all(".job-card-container")
            logger.info("LinkedIn: found %d job cards", len(cards))

            for card in cards[: params.max_results]:
                try:
                    title_el = card.query_selector(".job-card-list__title")
                    company_el = card.query_selector(".job-card-container__company-name")
                    location_el = card.query_selector(".job-card-container__metadata-wrapper")
                    url_el = card.query_selector("a")

                    title = title_el.inner_text().strip() if title_el else ""
                    company = company_el.inner_text().strip() if company_el else ""
                    loc = location_el.inner_text().strip() if location_el else ""
                    url = url_el.get_attribute("href") if url_el else ""

                    job = self.normalise(
                        title=title,
                        company=company,
                        description="",  # Would need to click into each listing
                        location=loc,
                        url=f"https://www.linkedin.com{url}" if url and url.startswith("/") else url,
                        remote="remote" in loc.lower(),
                    )
                    jobs.append(job)
                except Exception as e:
                    logger.debug("Error parsing LinkedIn card: %s", e)
                    continue

        except Exception as e:
            logger.warning("LinkedIn scraping failed: %s", e)
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass

        logger.info("LinkedIn: %d jobs collected", len(jobs))
        return jobs


class IndeedSource(PlaywrightSource):
    """Indeed job search scraper using Playwright."""

    @property
    def name(self) -> str:
        return "indeed"

    def search(self, params: SearchParams) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        page = browser = playwright = None

        try:
            page, browser, playwright = self._get_page()

            query = params.role.replace(" ", "+")
            location = params.location.replace(" ", "+") if params.location else ""
            search_url = (
                f"https://www.indeed.com/jobs?"
                f"q={query}"
                f"&l={location}"
                f"&fromage={params.days_old}"
            )
            if params.remote:
                search_url += "&remotejob=1"

            page.goto(search_url, wait_until="domcontentloaded")
            self._delay(3, 5)

            # Scroll to load
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 600)")
                self._delay(0.5, 1)

            cards = page.query_selector_all(".job_seen_beacon")
            logger.info("Indeed: found %d job cards", len(cards))

            for card in cards[: params.max_results]:
                try:
                    title_el = card.query_selector("h2.jobTitle a")
                    company_el = card.query_selector("[data-testid=company-name]")
                    location_el = card.query_selector("[data-testid=text-location]")
                    salary_el = card.query_selector("[data-testid=attribute-text]")

                    title = title_el.inner_text().strip() if title_el else ""
                    href = title_el.get_attribute("href") if title_el else ""
                    company = company_el.inner_text().strip() if company_el else ""
                    loc = location_el.inner_text().strip() if location_el else ""
                    salary = salary_el.inner_text().strip() if salary_el else None

                    job = self.normalise(
                        title=title,
                        company=company,
                        description="",  # Would need to open detail page
                        location=loc,
                        url=f"https://www.indeed.com{href}" if href else "",
                        salary_range=salary,
                        remote="remote" in loc.lower(),
                    )
                    jobs.append(job)
                except Exception as e:
                    logger.debug("Error parsing Indeed card: %s", e)
                    continue

        except Exception as e:
            logger.warning("Indeed scraping failed: %s", e)
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass

        logger.info("Indeed: %d jobs collected", len(jobs))
        return jobs


# ─── Jobicy API adapter (no API key needed) ─────────────────────────────────

class JobicySource(JobSource):
    """Jobicy remote job board — free, no API key needed, remote-native.
    API: https://jobicy.com/api/v2/remote-jobs
    """

    BASE_URL = "https://jobicy.com/api/v2/remote-jobs"

    @property
    def name(self) -> str:
        return "jobicy"

    def search(self, params: SearchParams) -> list[JobPosting]:
        import httpx

        # Build query parameters
        query_params = {
            "count": min(params.max_results, 50),
            "tag": params.role or "",
        }
        # Jobicy is remote-native, so no explicit remote parameter needed

        try:
            resp = httpx.get(self.BASE_URL, params=query_params, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            raw_jobs = data.get("jobs", [])
            if not raw_jobs:
                logger.info("Jobicy: no jobs found for '%s'", params.role)
                return []

            jobs: list[JobPosting] = []
            now = datetime.now(timezone.utc)

            for raw in raw_jobs:
                title = raw.get("jobTitle", "") or ""
                company = raw.get("companyName", "Unknown") or "Unknown"
                description = raw.get("jobDescription", "") or ""
                url = raw.get("url", "") or ""
                location = raw.get("jobLocation", "Remote") or "Remote"
                salary_min = raw.get("annualSalaryMin")
                salary_max = raw.get("annualSalaryMax")
                currency = raw.get("currency", "USD")
                pub_date_str = raw.get("pubDate", "")
                industry = raw.get("jobIndustry", [])
                job_type = raw.get("jobType", [])

                # Filter by recency — only include jobs posted within days_old
                if pub_date_str:
                    try:
                        pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d %H:%M:%S")
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                        days_diff = (now - pub_date).days
                        if days_diff > params.days_old:
                            continue  # Skip jobs older than days_old
                    except ValueError:
                        pass  # Can't parse date, include anyway

                # Build salary string
                salary = None
                if salary_min and salary_max:
                    try:
                        s_min = float(salary_min)
                        s_max = float(salary_max)
                        if currency == "USD":
                            salary = f"${s_min:,.0f} - ${s_max:,.0f}"
                        else:
                            salary = f"{currency} {s_min:,.0f} - {s_max:,.0f}"
                    except (ValueError, TypeError):
                        pass

                # Detect skills from description + industry tags
                skills_list: list[str] = []
                if description:
                    # Extract common PM-relevant keywords
                    pm_keywords = [
                        "product management", "product strategy", "roadmap",
                        "agile", "scrum", "user research", "analytics",
                        "a/b testing", "stakeholder", "sprint", "backlog",
                        "kpi", "okr", "data-driven", "cross-functional",
                        "product lifecycle", "user stories", "feature prioritization",
                    ]
                    desc_lower = description.lower()
                    for kw in pm_keywords:
                        if kw in desc_lower:
                            skills_list.append(kw.title())
                if industry and isinstance(industry, list):
                    for ind in industry:
                        if ind not in skills_list:
                            skills_list.append(ind)

                seniority = self._detect_seniority(title, description)

                job = self.normalise(
                    title=title,
                    company=company,
                    description=description,
                    location=location,
                    url=url,
                    salary_range=salary,
                    remote=True,  # Jobicy is remote-native
                    skills=skills_list[:15],
                )
                # Override seniority from detection (normalise also detects)
                job.seniority = seniority
                jobs.append(job)

            logger.info("Jobicy: found %d jobs for '%s' (filtered %d total)", len(jobs), params.role, len(raw_jobs))
            return jobs

        except httpx.HTTPStatusError as e:
            logger.warning("Jobicy HTTP error: %s", e)
            return []
        except httpx.RequestError as e:
            logger.warning("Jobicy request failed: %s", e)
            return []
        except Exception as e:
            logger.warning("Jobicy search failed: %s", e)
            return []


# ─── Firecrawl web scraper adapter (free tier: 1,000 pages/month) ──────────
# Scrapes Indeed (and potentially other public job boards) via Firecrawl API.
# - LinkedIn: Firecrawl blocks (403 error) — skip
# - Indeed: Works. Uses HTML parsing via BeautifulSoup for robust extraction.
# Each daily run uses ~1-2 pages = ~30-60 pages/month, well within free tier.

class FirecrawlSource(JobSource):
    """Job scraper using Firecrawl API — no browser needed, handles anti-bot.
    Free tier: 1,000 pages/month. Each daily run uses ~1-2 pages (~30-60/month).

    Currently scrapes:
      - Indeed (via BeautifulSoup HTML parsing)

    Not supported:
      - LinkedIn (Firecrawl blocks with 403)
    """

    FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"

    @property
    def name(self) -> str:
        return "firecrawl"

    def search(self, params: SearchParams) -> list[JobPosting]:
        api_key = settings.firecrawl_api_key or None
        if not api_key:
            logger.info("Firecrawl: no API key configured — skipping")
            return []

        jobs: list[JobPosting] = []
        seen_urls: set[str] = set()

        # Scrape Indeed (the only supported board currently)
        indeed_jobs = self._scrape_indeed(params, api_key)
        for j in indeed_jobs:
            if j.url and j.url not in seen_urls:
                seen_urls.add(j.url)
                jobs.append(j)

        logger.info(
            "Firecrawl: %d jobs from Indeed (requested: %s, days_old: %d)",
            len(jobs),
            params.role,
            params.days_old,
        )
        return jobs

    # ─── Indeed scraping ───────────────────────────────────────────────────────

    def _scrape_indeed(
        self, params: SearchParams, api_key: str
    ) -> list[JobPosting]:
        """Scrape Indeed job search via Firecrawl + BeautifulSoup HTML parsing."""
        query = params.role.replace(" ", "+")
        search_url = (
            f"https://www.indeed.com/jobs?"
            f"q={query}"
            f"&remotejob=1"
            f"&fromage={params.days_old}"
        )

        html_content = self._fetch_html_via_firecrawl(search_url, api_key)
        if not html_content:
            return []

        return self._parse_indeed_html(html_content, params.max_results)

    def _fetch_html_via_firecrawl(
        self, url: str, api_key: str
    ) -> str | None:
        """Fetch a URL via Firecrawl scrape API and return the HTML content."""
        import httpx

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        payload = {
            "url": url,
            "formats": ["html", "markdown"],
            "onlyMainContent": False,
        }

        try:
            resp = httpx.post(
                self.FIRECRAWL_API_URL,
                json=payload,
                headers=headers,
                timeout=45,
            )
            resp.raise_for_status()
            data = resp.json()

            if not data.get("success"):
                logger.warning(
                    "Firecrawl scrape failed for %s: %s",
                    url,
                    data.get("error", "unknown"),
                )
                return None

            html = data.get("data", {}).get("html", "")
            if not html:
                logger.warning("Firecrawl returned empty HTML for %s", url)
                return None

            return html

        except httpx.HTTPStatusError as e:
            logger.warning("Firecrawl HTTP error scraping %s: %s", url, e)
            return None
        except httpx.RequestError as e:
            logger.warning("Firecrawl request failed for %s: %s", url, e)
            return None
        except Exception as e:
            logger.warning("Firecrawl error for %s: %s", url, e)
            return None

    def _parse_indeed_html(
        self, html: str, max_results: int
    ) -> list[JobPosting]:
        """Parse Indeed job listings from HTML using BeautifulSoup.

        Indeed DOM structure (observed Jan 2025):
          td.resultContent
            ├── div (title container, css-pt3vth)
            │   └── h3.jobTitle
            │       └── a.jcs-JobTitle  ← title text + data-jk attribute + href
            └── div (company/location, css-u74ql7)
                └── (company name text + location text, often combined)
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobPosting] = []
        seen_jks: set[str] = set()

        # Find job title links — most reliable selector on Indeed
        title_links = soup.select("h3.jobTitle a.jcs-JobTitle")

        if not title_links:
            logger.warning(
                "Firecrawl Indeed: no job title elements found. "
                "HTML length: %d chars. First 500: %s",
                len(html),
                html[:500],
            )
            return []

        logger.info("Firecrawl Indeed: found %d job title elements", len(title_links))

        for link in title_links[:max_results]:
            try:
                title = link.get_text(strip=True)
                jk = link.get("data-jk", "")
                href = link.get("href", "")

                if not title or not jk:
                    continue

                # Dedup by data-jk
                if jk in seen_jks:
                    continue
                seen_jks.add(jk)

                # Build full URL
                full_url = f"https://www.indeed.com{href}" if href.startswith("/") else href

                # Find the parent td.resultContent to get company/location
                parent_td = link.find_parent("td", class_="resultContent")
                company = ""
                location = ""
                salary = None

                if parent_td:
                    # The company/location is in a sibling div of the title container
                    # We look for all non-title content within the td
                    all_divs = parent_td.find_all("div", recursive=True)
                    for div in all_divs:
                        cls = " ".join(div.get("class", []))
                        txt = div.get_text(strip=True)

                        # Skip the title div itself
                        if "jobTitle" in cls or "jcs-JobTitle" in cls or "css-pt3vth" in cls:
                            continue

                        if not txt or len(txt) < 3:
                            continue

                        # Try to separate company and location
                        # Indeed often puts them together like "CompanyNameRemote in City, State"
                        if not company:
                            if "\n" in txt:
                                parts = [p.strip() for p in txt.split("\n") if p.strip()]
                                company = parts[0] if parts else txt
                                location = parts[1] if len(parts) > 1 else ""
                            else:
                                company = txt
                        elif not location:
                            location = txt

                        # Check for salary
                        if "$" in txt and not salary and any(c.isdigit() for c in txt):
                            salary = txt[:120]

                    # Fallback: look for meta/salary containers
                    if not salary:
                        meta_els = parent_td.select("[class*=salary], [class*=meta], [data-testid*=salary]")
                        for m in meta_els:
                            txt = m.get_text(strip=True)
                            if txt and "$" in txt:
                                salary = txt[:120]
                                break

                # Heuristic: separate company from location if they're fused
                # Indeed often writes: "CompanyNameRemote in City, State" or "CompanyNameCity, State"
                if company and not location:
                    # Company may contain location info — try to split
                    for sep in ["Remote in ", "remote in ", "Remote.", " - ", " · "]:
                        if sep in company:
                            parts = company.split(sep, 1)
                            company = parts[0].strip()
                            location = (sep.strip() + " " + parts[1].strip()).strip()
                            break

                if not company:
                    company = "Indeed"
                if not location:
                    location = "Remote"

                job = self.normalise(
                    title=title,
                    company=company,
                    description="",
                    location=location,
                    url=full_url,
                    salary_range=salary,
                    remote="remote" in location.lower(),
                )
                # source is set by normalise() from self.name
                jobs.append(job)

            except Exception as e:
                logger.debug("Error parsing Indeed job card: %s", e)
                continue

        logger.info("Firecrawl Indeed: parsed %d jobs from HTML", len(jobs))
        return jobs


# ─── Orchestrator ───────────────────────────────────────────────────────────

class JobDiscovery:
    """Orchestrates multi-source job search with deduplication."""

    def __init__(self):
        self.sources: list[JobSource] = [
            JobicySource(),
            AdzunaSource(),
            LinkedInSource(),
            IndeedSource(),
        ]
        self._seen_ids: set[str] = set()

    def search(self, params: SearchParams) -> SearchResult:
        """Query all sources, deduplicate, and return aggregated results."""
        result = SearchResult()
        self._seen_ids.clear()

        for source in self.sources:
            try:
                jobs = source.search(params)
                result.source_counts[source.name] = len(jobs)

                for job in jobs:
                    if job.id not in self._seen_ids:
                        self._seen_ids.add(job.id)
                        result.jobs.append(job)
                    else:
                        logger.debug("Deduplicated duplicate job: %s @ %s", job.title, job.company)

            except Exception as e:
                msg = f"{source.name}: {e}"
                logger.warning("Job source error — %s", msg)
                result.errors.append(msg)

        # Sort by seniority (more senior first) as a rough proxy for relevance
        seniority_order = {
            SeniorityLevel.EXECUTIVE: 0,
            SeniorityLevel.PRINCIPAL: 1,
            SeniorityLevel.STAFF: 2,
            SeniorityLevel.SENIOR: 3,
            SeniorityLevel.MID: 4,
            SeniorityLevel.JUNIOR: 5,
            SeniorityLevel.ENTRY: 6,
            SeniorityLevel.UNKNOWN: 7,
        }
        result.jobs.sort(key=lambda j: seniority_order.get(j.seniority, 7))

        logger.info(
            "JobDiscovery: %d unique jobs from %d sources",
            len(result.jobs),
            len(result.source_counts),
        )
        return result

    def search_and_store(self, params: SearchParams) -> SearchResult:
        """Search for jobs and persist them to the JSON store."""
        result = self.search(params)
        if result.jobs:
            from backend.database import storage
            storage.save_jobs([j.model_dump(mode="json") for j in result.jobs])
            logger.info("Saved %d jobs to storage", len(result.jobs))
        return result
