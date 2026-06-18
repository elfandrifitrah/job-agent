"""
CV Parser — extracts structured candidate data from PDF and DOCX files.

Pipeline:
  1. Text extraction (pdfplumber / python-docx / plain text)
  2. Regex-based entity extraction (email, phone, URLs)
  3. spaCy NER for organisations, persons, locations
  4. Skill keyword matching against a built-in taxonomy
  5. Role / title extraction using heuristics
  6. Seniority classification
  7. CandidateProfile assembly
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from backend.models.profile import (
    CandidateProfile,
    Education,
    Experience,
    SeniorityLevel,
    Skill,
)

logger = logging.getLogger(__name__)

# ─── Built-in skill taxonomy ────────────────────────────────────────────────
SKILL_TAXONOMY: dict[str, list[str]] = {
    "language": [
        "python", "javascript", "typescript", "java", "c#", "c++", "go", "rust",
        "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "sql",
        "bash", "powershell", "perl", "lua", "dart",
    ],
    "framework": [
        "react", "angular", "vue", "django", "flask", "fastapi", "spring",
        "rails", "express", "next.js", "nuxt", "svelte", "tensorflow",
        "pytorch", "pandas", "numpy", "scikit-learn", "langchain",
        "node.js", "dotnet", "laravel", "symfony",
    ],
    "cloud": [
        "aws", "azure", "gcp", "cloud", "docker", "kubernetes", "terraform",
        "ci/cd", "jenkins", "github actions", "gitlab ci", "serverless",
    ],
    "database": [
        "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch",
        "dynamodb", "cassandra", "sqlite", "bigquery", "snowflake",
        "oracle", "sql server",
    ],
    "tool": [
        "git", "docker", "kubernetes", "jira", "confluence", "figma",
        "sketch", "photoshop", "tableau", "power bi", "grafana",
        "prometheus", "datadog", "new relic",
    ],
    "soft": [
        "leadership", "communication", "teamwork", "project management",
        "agile", "scrum", "mentoring", "problem solving", "critical thinking",
        "public speaking", "negotiation", "collaboration",
    ],
}


# ─── Regex patterns ─────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?"          # country code
    r"(?:\(?\d{2,4}\)?[-.\s]?)"        # area code
    r"\d{3,4}[-.\s]?\d{3,4}"          # local number
)
URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"         # protocol & www
    r"(?:linkedin\.com|github\.com|gitlab\.com|bitbucket\.org)"
    r"/[a-zA-Z0-9_-]+/?",
)

SENIORITY_PATTERNS: list[tuple[re.Pattern, SeniorityLevel]] = [
    (re.compile(r"\b(principal|staff|architect)\b", re.I), SeniorityLevel.PRINCIPAL),
    (re.compile(r"\bsenior\b", re.I), SeniorityLevel.SENIOR),
    (re.compile(r"\b(mid(-level)?|intermediate)\b", re.I), SeniorityLevel.MID),
    (re.compile(r"\bjunior\b", re.I), SeniorityLevel.JUNIOR),
    (re.compile(r"\b(entry|graduate|intern)\b", re.I), SeniorityLevel.ENTRY),
    (re.compile(r"\b(vp|vice president|director|head of|chief|cx?o)\b", re.I), SeniorityLevel.EXECUTIVE),
]


def extract_name(text: str) -> str:
    """Extract the candidate's full name from the top of the CV text.

    Heuristic: the name is usually the first meaningful line that appears
    before contact details (email, phone, URLs). It should:
    - Be 2-4 words long
    - Have each word start with an uppercase letter
    - Not contain email/phone/URL patterns
    - Not contain job title or section keywords
    - Be less than 50 characters
    """
    lines = text.split("\n")

    # Keywords that indicate a line is NOT a name (section headers, role titles, etc.)
    NON_NAME_KEYWORDS = re.compile(
        r"\b(experience|education|skills|summary|profile|objective|"
        r"engineer|developer|architect|scientist|manager|director|"
        r"consultant|specialist|intern|lead|head|vice president)\b",
        re.I,
    )

    for line in lines:
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip lines that look like contact info
        if EMAIL_RE.search(line):
            continue
        if PHONE_RE.search(line):
            continue
        if URL_RE.search(line):
            continue

        # Skip lines that are too short or too long
        if len(line) < 3 or len(line) > 50:
            continue

        # Skip lines containing job title/section keywords
        if NON_NAME_KEYWORDS.search(line):
            continue

        # Skip lines that look like company names (often start with "At " or "@")
        if line.lower().startswith("at ") or line.startswith("@"):
            continue

        # A name should have 2-4 words
        words = line.split()
        if len(words) < 2 or len(words) > 4:
            continue

        # A name should have each word capitalised (or at least mostly)
        capitalised_count = sum(1 for w in words if w[0].isupper())
        if capitalised_count < len(words) // 2:
            continue

        # Skip numbered lines, lines with special characters, or date patterns
        # Use a single-quoted raw string to avoid issues with double-quote inside
        if re.search(r'^\d+\.?\s|\d{4}|^[\-*]|\\|"|""', line):
            continue

        # This looks like a name!
        return line.strip()

    return ""


def extract_email(text: str) -> str:
    match = EMAIL_RE.search(text)
    return match.group(0) if match else ""


def extract_phone(text: str) -> str:
    match = PHONE_RE.search(text)
    return match.group(0).strip() if match else ""


def extract_urls(text: str) -> dict[str, str]:
    urls: dict[str, str] = {}
    for match in URL_RE.finditer(text):
        url = match.group(0)
        if "linkedin" in url.lower() and not urls.get("linkedin"):
            urls["linkedin"] = url
        elif "github" in url.lower() and not urls.get("github"):
            urls["github"] = url
    return urls


def extract_skills(text: str) -> list[Skill]:
    """Match lowercase text against the skill taxonomy."""
    lower = text.lower()
    found: dict[str, Skill] = {}
    for category, keywords in SKILL_TAXONOMY.items():
        for kw in keywords:
            # Build a word-boundary pattern for all keywords (single or multi-word)
            pattern = r"\b" + re.escape(kw) + r"\b"
            for m in re.finditer(pattern, lower):
                name = m.group(0).title()
                if name not in found:
                    found[name] = Skill(name=name, category=category, confidence=0.8 if " " not in kw else 0.7, mentions=0)
                found[name].mentions += 1
        # Cap confidence
        for s in found.values():
            s.confidence = min(s.confidence + (s.mentions - 1) * 0.05, 0.98)
    return sorted(found.values(), key=lambda s: s.mentions, reverse=True)


def extract_roles(text: str) -> list[str]:
    """Extract likely job titles using patterns.
    This is a heuristic — real NER would be better (spaCy).
    """
    lines = text.split("\n")
    roles = []
    title_patterns = [
        r"\b(?:software|senior|lead|principal|staff)?\s*"
        r"(?:engineer|developer|architect|scientist|analyst|manager|"
        r"designer|director|consultant|specialist|intern)\b",
    ]
    for line in lines:
        line = line.strip()
        for pat in title_patterns:
            if re.search(pat, line, re.I) and len(line) < 80:
                roles.append(line)
                break
    return roles[:8]


def detect_seniority(text: str, title: str = "") -> SeniorityLevel:
    """Classify seniority based on text content and title."""
    corpus = f"{text} {title}"
    for pattern, level in SENIORITY_PATTERNS:
        if pattern.search(corpus):
            return level
    return SeniorityLevel.UNKNOWN


def estimate_experience_years(experiences: list[Experience]) -> float:
    """Sum up total years of experience from date ranges."""
    total = 0.0
    for exp in experiences:
        if exp.years_at_role:
            total += exp.years_at_role
        elif exp.start_date and exp.end_date:
            total += 1.0  # fallback — estimate 1 year per role
    return round(total, 1)


def parse_experiences(text: str) -> list[Experience]:
    """Heuristic experience extraction from raw CV text.

    Supports multiple CV layout patterns:
      - "Company — Title" (em-dash / en-dash)
      - "Company | Title"
      - "Title at Company"
      - "Company / Title"
      - Date-prefixed lines followed by company + title

    Fallback: any line containing a common job title keyword is captured as a role.
    Phase 2 will replace this with LLM-powered extraction.
    """
    experiences: list[Experience] = []
    lines = text.split("\n")
    current_company = ""
    current_title = ""
    current_desc_lines: list[str] = []

    # Common title keywords to detect role lines
    TITLE_KW = re.compile(
        r"\b(engineer|developer|architect|scientist|analyst|manager|"
        r"designer|director|consultant|intern|lead|head|vp|chief)\b",
        re.I,
    )

    def flush() -> None:
        if current_company or current_title:
            exp = Experience(
                company=current_company.strip(),
                title=current_title.strip(),
                description=" ".join(current_desc_lines).strip(),
            )
            experiences.append(exp)

    # Try date-range prefix: "Jan 2020 - Present" or "2021-2023"
    date_prefix = re.compile(r"^[A-Z][a-z]+\s+\d{4}\s*[–-]|^\d{4}\s*[–-]", re.I)

    for line in lines:
        line = line.strip()
        if not line:
            continue

        stripped = date_prefix.sub("", line).strip()
        role_line = stripped or line

        # Pattern 1: "Company — Title" or "Company | Title" or "Company / Title"
        sep_match = re.match(r"^(.+?)\s*[—–|/:]\s*(.+)$", role_line)
        if sep_match and TITLE_KW.search(sep_match.group(2)):
            flush()
            current_company = sep_match.group(1).strip()
            current_title = sep_match.group(2).strip()
            current_desc_lines = []
            continue

        # Pattern 2: "Title at Company"
        at_match = re.match(r"^(.+?)\s+at\s+(.+)$", role_line, re.I)
        if at_match and TITLE_KW.search(at_match.group(1)):
            flush()
            current_title = at_match.group(1).strip()
            current_company = at_match.group(2).strip()
            current_desc_lines = []
            continue

        # Pattern 3: Line looks like a standalone company name (capitalised, short)
        if (
            re.match(r"^[A-Z][A-Za-z\s&.,]+$", role_line)
            and 3 < len(role_line) < 60
            and not TITLE_KW.search(role_line)
        ):
            flush()
            current_company = role_line
            current_title = ""
            current_desc_lines = []
            continue

        # Pattern 4: Line starts with a title keyword (standalone title line)
        if TITLE_KW.match(role_line) and len(role_line) < 60:
            if current_company:
                flush()
            current_title = role_line
            current_desc_lines = []
            continue

        # Otherwise accumulate as description
        if current_company or current_title:
            current_desc_lines.append(line)

    flush()
    return experiences


def extract_education(text: str) -> list[Education]:
    """Simple education extraction heuristic."""
    entries: list[Education] = []
    edu_keywords = re.compile(
        r"\b(bachelor|master|ph\.?d|doctorate|associate|"
        r"b\.?s\.?c\.?|m\.?s\.?c\.?|b\.?a\.?|m\.?a\.?|"
        r"university|college|institute|school)\b",
        re.I,
    )
    lines = text.split("\n")
    for line in lines:
        if edu_keywords.search(line) and len(line) < 120:
            entries.append(Education(institution=line.strip()))
    return entries


class CVParser:
    """Main parser — extracts a CandidateProfile from a CV file."""

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".html"}

    def __init__(self) -> None:
        self._has_spacy = False
        try:
            import spacy  # noqa: F401
            self._has_spacy = True
        except ImportError:
            logger.info("spaCy not available — falling back to regex-only extraction")

    def parse(self, file_path: str | Path) -> CandidateProfile:
        """Parse a CV file and return a structured CandidateProfile."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CV not found: {path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext} (supported: {self.SUPPORTED_EXTENSIONS})")

        raw_text = self._extract_text(path)
        profile = self._build_profile(raw_text, str(path))
        return profile

    def _extract_text(self, path: Path) -> str:
        """Extract raw text from various file formats."""
        ext = path.suffix.lower()
        if ext == ".pdf":
            return self._extract_pdf(path)
        elif ext == ".docx":
            return self._extract_docx(path)
        elif ext == ".txt":
            return path.read_text(encoding="utf-8", errors="replace")
        elif ext == ".html":
            return self._extract_html(path)
        return ""

    def _extract_pdf(self, path: Path) -> str:
        """Extract text from a PDF using pdfplumber."""
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
                return "\n".join(pages)
        except ImportError:
            logger.warning("pdfplumber not installed. Attempting fallback...")
            raise
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            return ""

    def _extract_docx(self, path: Path) -> str:
        """Extract text from a DOCX using python-docx."""
        try:
            from docx import Document
            doc = Document(path)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            logger.warning("python-docx not installed.")
            raise
        except Exception as e:
            logger.error(f"DOCX extraction failed: {e}")
            return ""

    def _extract_html(self, path: Path) -> str:
        """Basic HTML text extraction (strip tags)."""
        import html as html_mod
        text = path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", text)
        text = html_mod.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _build_profile(self, raw_text: str, source_file: str) -> CandidateProfile:
        """Assemble a CandidateProfile from raw text."""
        text = raw_text.strip()
        if not text:
            raise ValueError("No text could be extracted from the CV file.")

        urls = extract_urls(text)
        experiences = parse_experiences(text)
        skills = extract_skills(text)
        education = extract_education(text)

        # Determine seniority from text
        title = experiences[0].title if experiences else ""
        seniority = detect_seniority(text, title)

        profile = CandidateProfile(
            full_name=extract_name(text),
            raw_text=text[:10_000],  # cap at 10k chars for storage
            email=extract_email(text),
            phone=extract_phone(text),
            linkedin_url=urls.get("linkedin", ""),
            github_url=urls.get("github", ""),
            skills=skills,
            experiences=experiences,
            education=education,
            years_of_experience=estimate_experience_years(experiences),
            seniority=seniority,
            target_roles=extract_roles(text),
            source_file=source_file,
        )

        logger.info(
            "Parsed CV: %s | %d skills | %d roles | %s",
            profile.full_name or "Unknown",
            len(profile.skills),
            len(profile.experiences),
            profile.seniority.value,
        )
        return profile
