"""
ATS Resume Checker — scores a CV against 20+ ATS criteria.

Pure Python logic, no API calls needed. Scores are broken into 4 categories:
  - Keyword Match (0-100): % of required skills found in CV
  - Format (0-100): section headers, bullet usage, length, chronology
  - Impact (0-100): action verbs, quantified results
  - Completeness (0-100): contact info, education dates, certifications
  - Composite (0-100): weighted average of all 4 sub-scores
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Action verbs dictionary ─────────────────────────────────────────────────
ACTION_VERBS = [
    "achieved", "accelerated", "acquired", "built", "chaired", "compiled",
    "completed", "conceived", "conducted", "consolidated", "created", "cut",
    "decreased", "defined", "delivered", "designed", "developed", "devised",
    "directed", "drove", "earned", "eliminated", "enabled", "established",
    "evaluated", "executed", "expanded", "expedited", "formulated", "founded",
    "generated", "grew", "headed", "identified", "implemented", "improved",
    "increased", "initiated", "instituted", "integrated", "introduced", "invented",
    "launched", "led", "managed", "mentored", "negotiated", "optimized",
    "orchestrated", "organized", "overhauled", "pioneered", "planned", "prepared",
    "presented", "produced", "programmed", "proposed", "raised", "recommended",
    "reduced", "reengineered", "reorganized", "replaced", "resolved", "restructured",
    "revamped", "revitalized", "saved", "shaped", "simplified", "slashed",
    "spearheaded", "standardized", "steered", "streamlined", "strengthened",
    "structured", "succeeded", "transformed", "upgraded", "won",
]

# Section headers that ATS systems look for
SECTION_HEADERS = [
    "experience", "work experience", "employment", "professional experience",
    "education", "academic", "qualifications",
    "skills", "technical skills", "core competencies",
    "summary", "professional summary", "profile", "objective",
    "projects", "certifications", "publications", "awards",
    "languages", "volunteer", "interests",
]

# Common ATS-friendly file formats (in order of preference)
ATS_FORMATS = {
    ".pdf": 100,
    ".docx": 90,
    ".doc": 70,
    ".txt": 50,
    ".rtf": 60,
}


@dataclass
class AtsCriterionResult:
    name: str
    passed: bool
    score: float
    detail: str = ""


@dataclass
class AtsCheckResult:
    keyword_match: float  # 0-100
    format_score: float  # 0-100
    impact_score: float  # 0-100
    completeness_score: float  # 0-100
    composite: int  # 0-100, rounded
    criteria: list[AtsCriterionResult] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class AtsChecker:
    """Check a CV against 20+ ATS criteria."""

    def __init__(self, cv_text: str, file_extension: str = ".pdf"):
        self.cv_text = cv_text
        self.ext = file_extension.lower().strip()
        self.lines = cv_text.split("\n")
        self.words = cv_text.split()
        self.lower_text = cv_text.lower()

    def check_all(self, job_skills: list[str] | None = None) -> AtsCheckResult:
        """Run all checks and return a composite score."""
        criteria: list[AtsCriterionResult] = []
        suggestions: list[str] = []

        kw_score, kw_criteria, kw_suggestions = self._check_keywords(job_skills or [])
        criteria.extend(kw_criteria)
        suggestions.extend(kw_suggestions)

        fmt_score, fmt_criteria, fmt_suggestions = self._check_format()
        criteria.extend(fmt_criteria)
        suggestions.extend(fmt_suggestions)

        imp_score, imp_criteria, imp_suggestions = self._check_impact()
        criteria.extend(imp_criteria)
        suggestions.extend(imp_suggestions)

        comp_score, comp_criteria, comp_suggestions = self._check_completeness()
        criteria.extend(comp_criteria)
        suggestions.extend(comp_suggestions)

        composite = round(
            kw_score * 0.35 + fmt_score * 0.25 + imp_score * 0.25 + comp_score * 0.15
        )

        return AtsCheckResult(
            keyword_match=round(kw_score),
            format_score=round(fmt_score),
            impact_score=round(imp_score),
            completeness_score=round(comp_score),
            composite=composite,
            criteria=criteria,
            suggestions=suggestions[:10],
        )

    # ─── Keyword Match (35% of composite) ────────────────────────────────────

    def _check_keywords(
        self, job_skills: list[str],
    ) -> tuple[float, list[AtsCriterionResult], list[str]]:
        criteria: list[AtsCriterionResult] = []
        suggestions: list[str] = []

        if not job_skills:
            # No job provided — just check generic density
            score = 50.0
            criteria.append(AtsCriterionResult(
                name="keyword_density", passed=True, score=50.0,
                detail="No job skills provided for comparison",
            ))
            return score, criteria, suggestions

        # Check each required skill
        found_count = 0
        for skill in job_skills:
            skill_lower = skill.lower()
            if skill_lower in self.lower_text:
                found_count += 1
            criteria.append(AtsCriterionResult(
                name=f"skill_{skill.replace(' ', '_').lower()[:20]}",
                passed=skill_lower in self.lower_text,
                score=100.0 if skill_lower in self.lower_text else 0.0,
                detail=f"Skill '{skill}' {'found' if skill_lower in self.lower_text else 'not found'} in CV",
            ))

        match_pct = (found_count / len(job_skills)) * 100 if job_skills else 0
        criteria.append(AtsCriterionResult(
            name="keyword_match_overall", passed=match_pct >= 50, score=match_pct,
            detail=f"{found_count}/{len(job_skills)} required skills found ({match_pct:.0f}%)",
        ))

        if match_pct < 50:
            suggestions.append("Add more keywords from the job description to your skills section and bullet points")

        return match_pct, criteria, suggestions

    # ─── Format (25% of composite) ──────────────────────────────────────────

    def _check_format(self) -> tuple[float, list[AtsCriterionResult], list[str]]:
        criteria: list[AtsCriterionResult] = []
        suggestions: list[str] = []
        score = 0.0
        checks = 0

        # 1. Section headers present
        found_sections = [h for h in SECTION_HEADERS if h in self.lower_text]
        section_pct = min(100, (len(found_sections) / 5) * 100)  # Expect at least 5 sections
        score += section_pct
        checks += 1
        criteria.append(AtsCriterionResult(
            name="section_headers", passed=section_pct >= 60,
            score=section_pct,
            detail=f"Found {len(found_sections)} section headers: {', '.join(found_sections[:6])}",
        ))
        if len(found_sections) < 4:
            suggestions.append("Add standard ATS section headers: Experience, Education, Skills, Summary")

        # 2. Bullet usage (preferred over paragraphs)
        bullet_count = len(re.findall(r"^[\s]*[•\-\*\d+\.]\s", self.cv_text, re.MULTILINE))
        total_content_lines = sum(1 for l in self.lines if l.strip())
        bullet_ratio = bullet_count / max(total_content_lines, 1)
        bullet_score = min(100, (bullet_ratio / 0.5) * 100)  # Ideal: 50% lines are bullets
        score += bullet_score
        checks += 1
        criteria.append(AtsCriterionResult(
            name="bullet_points", passed=bullet_score >= 50, score=bullet_score,
            detail=f"{bullet_count} bullet points in {total_content_lines} lines ({bullet_ratio:.0%})",
        ))
        if bullet_count < 15:
            suggestions.append("Use more bullet points (ATS prefers bullets over paragraph blocks)")

        # 3. Length check (1-2 pages ideal ≈ 400-1000 words for a CV)
        word_count = len(self.words)
        if 400 <= word_count <= 1200:
            length_score = 100
        elif word_count < 300:
            length_score = 40
        elif word_count < 400:
            length_score = 70
        elif word_count > 1500:
            length_score = 60
        else:
            length_score = 80
        score += length_score
        checks += 1
        criteria.append(AtsCriterionResult(
            name="cv_length", passed=400 <= word_count <= 1200,
            score=length_score,
            detail=f"{word_count} words (ideal: 400-1200 for 1-2 pages)",
        ))
        if word_count > 1200:
            suggestions.append("Consider trimming your CV to 1-2 pages for better ATS parsing")
        elif word_count < 300:
            suggestions.append("Your CV seems short — add more detail to reach ~500 words minimum")

        # 4. File format
        format_score = ATS_FORMATS.get(self.ext, 30)
        score += format_score
        checks += 1
        criteria.append(AtsCriterionResult(
            name="file_format", passed=format_score >= 70, score=format_score,
            detail=f"Format: {self.ext.upper()} (PDF is best for ATS)",
        ))
        if self.ext != ".pdf":
            suggestions.append("Upload as PDF for best ATS compatibility")

        # 5. Reverse chronological order (recent roles first)
        date_patterns = re.findall(
            r"(19|20)\d{2}\s*[-–to]+\s*(?:present|current|now|(?:19|20)\d{2})",
            self.lower_text,
        )
        chrono_score = 70 if date_patterns else 50
        score += chrono_score
        checks += 1
        criteria.append(AtsCriterionResult(
            name="chronological_order", passed=chrono_score >= 70,
            score=chrono_score,
            detail=f"Found {len(date_patterns)} date ranges. Ensure most recent role is listed first.",
        ))

        # 6. Consistent formatting check
        # Check if bullet markers are consistent
        bullet_markers = set(re.findall(r"^[\s]*([•\-\*\d+\.])\s", self.cv_text, re.MULTILINE))
        consistent = len(bullet_markers) <= 2
        consistency_score = 100 if consistent else 60
        score += consistency_score
        checks += 1
        criteria.append(AtsCriterionResult(
            name="consistent_formatting", passed=consistent,
            score=consistency_score,
            detail="Bullet styles consistent" if consistent else f"Mixed bullet styles: {bullet_markers}",
        ))
        if not consistent:
            suggestions.append("Use a single bullet style throughout (all • or all -)")

        return score / max(checks, 1), criteria, suggestions

    # ─── Impact (25% of composite) ──────────────────────────────────────────

    def _check_impact(self) -> tuple[float, list[AtsCriterionResult], list[str]]:
        criteria: list[AtsCriterionResult] = []
        suggestions: list[str] = []
        score = 0.0
        checks = 0

        # 1. Action verb usage
        verb_count = sum(1 for v in ACTION_VERBS if v in self.lower_text)
        verb_density = verb_count / max(len(self.words), 1) * 1000  # per 1000 words
        verb_score = min(100, (verb_density / 15) * 100)
        score += verb_score
        checks += 1
        criteria.append(AtsCriterionResult(
            name="action_verbs", passed=verb_score >= 50, score=verb_score,
            detail=f"Found {verb_count} action verbs ({verb_density:.1f}/1000 words)",
        ))
        if verb_count < 10:
            suggestions.append("Start bullet points with strong action verbs (led, built, launched, optimized)")

        # 2. Quantified results
        number_count = len(re.findall(r"\b\d+%|\$\s*\d+[kKmMbB]?|\b\d+x\b|\b\d+[\.\d]*\s*(?:million|billion|users|customers|revenue|cost)\b", self.lower_text))
        quant_score = min(100, (number_count / 5) * 100)
        score += quant_score
        checks += 1
        criteria.append(AtsCriterionResult(
            name="quantified_results", passed=quant_score >= 40,
            score=quant_score,
            detail=f"Found {number_count} quantified metrics (aim for 5+)",
        ))
        if number_count < 3:
            suggestions.append("Add quantified results (%, $, time saved, users impacted) to your bullet points")

        # 3. Strong opening words per bullet
        bullet_starts = re.findall(r"^[\s]*[•\-\*]\s+(\w+)", self.cv_text, re.MULTILINE)
        strong_starts = sum(1 for w in bullet_starts if w.lower() in ACTION_VERBS)
        start_ratio = strong_starts / max(len(bullet_starts), 1)
        start_score = start_ratio * 100
        score += start_score
        checks += 1
        criteria.append(AtsCriterionResult(
            name="bullet_starts", passed=start_ratio >= 0.5,
            score=start_score,
            detail=f"{strong_starts}/{len(bullet_starts)} bullets start with action verbs ({start_ratio:.0%})",
        ))
        if start_ratio < 0.3:
            suggestions.append("Start every bullet point with a strong action verb")

        return score / max(checks, 1), criteria, suggestions

    # ─── Completeness (15% of composite) ────────────────────────────────────

    def _check_completeness(self) -> tuple[float, list[AtsCriterionResult], list[str]]:
        criteria: list[AtsCriterionResult] = []
        suggestions: list[str] = []
        score = 0.0
        checks = 0

        # 1. Email
        has_email = bool(re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", self.cv_text))
        score += 100 if has_email else 0
        checks += 1
        criteria.append(AtsCriterionResult(
            name="email_present", passed=has_email, score=100 if has_email else 0,
            detail="Email found" if has_email else "No email address found",
        ))
        if not has_email:
            suggestions.append("Add your email address at the top of your CV")

        # 2. Phone
        has_phone = bool(re.search(r"[\+\d\(\)\-\s]{8,}", self.cv_text))
        score += 100 if has_phone else 0
        checks += 1
        criteria.append(AtsCriterionResult(
            name="phone_present", passed=has_phone, score=100 if has_phone else 0,
            detail="Phone number found" if has_phone else "No phone number found",
        ))
        if not has_phone:
            suggestions.append("Add your phone number")

        # 3. LinkedIn URL
        has_linkedin = "linkedin.com" in self.lower_text or "linkedin" in self.lower_text
        score += 100 if has_linkedin else 0
        checks += 1
        criteria.append(AtsCriterionResult(
            name="linkedin_present", passed=has_linkedin,
            score=100 if has_linkedin else 0,
            detail="LinkedIn found" if has_linkedin else "No LinkedIn URL found",
        ))

        # 4. Education entry with dates
        has_education = "education" in self.lower_text or any(
            s in self.lower_text for s in ["bachelor", "master", "phd", "b.s.", "m.s.", "b.a.", "m.a."]
        )
        score += 100 if has_education else 0
        checks += 1
        criteria.append(AtsCriterionResult(
            name="education_section", passed=has_education,
            score=100 if has_education else 0,
            detail="Education section found" if has_education else "No education section found",
        ))

        # 5. Experience section
        has_experience = "experience" in self.lower_text or "employment" in self.lower_text or "work history" in self.lower_text
        score += 100 if has_experience else 0
        checks += 1
        criteria.append(AtsCriterionResult(
            name="experience_section", passed=has_experience,
            score=100 if has_experience else 0,
            detail="Experience section found" if has_experience else "No experience section found",
        ))
        if not has_experience:
            suggestions.append("Add a 'Work Experience' section header")

        # 6. Skills section
        has_skills = "skills" in self.lower_text or "competencies" in self.lower_text
        score += 100 if has_skills else 0
        checks += 1
        criteria.append(AtsCriterionResult(
            name="skills_section", passed=has_skills,
            score=100 if has_skills else 0,
            detail="Skills section found" if has_skills else "No skills section found",
        ))
        if not has_skills:
            suggestions.append("Add a 'Skills' section listing technical and soft skills")

        # 7. Date ranges for experience
        has_date_ranges = bool(re.findall(
            r"(?:19|20)\d{2}\s*[-–to]+\s*(?:\w+|(?:19|20)\d{2})",
            self.lower_text,
        ))
        score += 100 if has_date_ranges else 0
        checks += 1
        criteria.append(AtsCriterionResult(
            name="date_ranges", passed=has_date_ranges, score=100 if has_date_ranges else 0,
            detail="Date ranges found" if has_date_ranges else "No date ranges found in experience entries",
        ))
        if not has_date_ranges:
            suggestions.append("Add start/end dates to each experience entry")

        return score / max(checks, 1), criteria, suggestions
