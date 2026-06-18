"""
Cover Letter Generator — produces tailored cover letters using LLMs.

Pipeline:
  1. Build a structured prompt from the CV profile + job posting
  2. Send to Claude API (primary) or OpenAI GPT-4 (fallback)
  3. Render through a Jinja2 template
  4. Export as PDF via WeasyPrint or plain text
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.models.profile import CandidateProfile, JobPosting, MatchResult

logger = logging.getLogger(__name__)

CV_TEMPLATE = """\
CANDIDATE PROFILE
=================
Name: {name}
Most recent role: {title}
Years of experience: {years_exp}
Seniority level: {seniority}

Key skills: {skills}

Experience:
{experience}

Education:
{education}
"""

JOB_TEMPLATE = """\
JOB POSTING
===========
Title: {title}
Company: {company}
Location: {location}
Remote: {remote}

Description:
{description}

Required skills: {skills_required}
"""

COVER_LETTER_SYSTEM_PROMPT = """\
You are an expert cover letter writer. Your task is to write a professional, \
tailored cover letter for the candidate described in the CANDIDATE PROFILE, \
applying for the JOB POSTING described below.

Guidelines:
- Be professional but personable — avoid generic boilerplate
- Highlight 2-3 specific achievements from the candidate's experience that \
align with the job requirements
- Reference specific skills from the candidate's profile that match the job's \
required skills
- Keep the letter between 250-350 words
- Do not include a subject line or address block — start with "Dear Hiring Manager,"
- End with "Sincerely," followed by the candidate's name
- Use the candidate's actual name from the profile (not "Alex Chen" if the \
name is different)
- Never fabricate experience or skills the candidate doesn't have
- If the match score is below 0.5, acknowledge the gap positively as "eager to develop"

Output only the cover letter text — no commentary, no preamble.
"""


class CoverLetterGenerator:
    """Generates tailored cover letters using LLM APIs."""

    # ─── Jinja2 templates directory ───
    TEMPLATES_DIR = Path(__file__).parent.parent.parent / "data" / "templates"

    def __init__(self):
        self.templates_dir = self.TEMPLATES_DIR
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self._jinja_env = None

    @property
    def jinja_env(self):
        if self._jinja_env is None:
            try:
                from jinja2 import Environment, FileSystemLoader
                self._jinja_env = Environment(
                    loader=FileSystemLoader(str(self.templates_dir)),
                    autoescape=False,
                )
            except ImportError:
                logger.warning("jinja2 not installed — falling back to plain-text generation")
                return None
        return self._jinja_env

    def _build_prompt(
        self,
        profile: CandidateProfile,
        job: JobPosting,
        match: Optional[MatchResult] = None,
    ) -> str:
        """Build the structured LLM prompt with CV + job context."""
        skills_str = ", ".join(profile.skill_names[:20])

        exp_lines = []
        for e in profile.experiences[:4]:
            exp_lines.append(f"  - {e.title} @ {e.company} ({e.start_date or ''} - {e.end_date or ''})")
            if e.description:
                # Truncate long descriptions
                desc = e.description[:200] + "..." if len(e.description) > 200 else e.description
                exp_lines.append(f"    {desc}")
        experience_str = "\n".join(exp_lines) if exp_lines else "N/A"

        edu_lines = []
        for e in profile.education[:3]:
            parts = [e.institution, e.degree, e.field]
            edu_lines.append("  - " + ", ".join(p for p in parts if p))
        education_str = "\n".join(edu_lines) if edu_lines else "N/A"

        cv_section = CV_TEMPLATE.format(
            name=profile.full_name or "The Candidate",
            title=profile.experiences[0].title if profile.experiences else "N/A",
            years_exp=profile.years_of_experience,
            seniority=profile.seniority.value,
            skills=skills_str,
            experience=experience_str,
            education=education_str,
        )

        job_section = JOB_TEMPLATE.format(
            title=job.title,
            company=job.company,
            location=job.location or "N/A",
            remote="Yes" if job.remote else "No",
            description=job.description,
            skills_required=", ".join(job.skills_required) if job.skills_required else "N/A",
        )

        if match:
            match_section = (
                f"\nMATCH CONTEXT\n"
                f"Match score: {match.score:.0%}\n"
                f"Skills overlap: {', '.join(match.skill_overlap[:10])}\n"
                f"Skill gaps to acknowledge: {', '.join(match.skill_gaps[:5])}"
            )
        else:
            match_section = ""

        return f"{cv_section}\n{job_section}\n{match_section}"

    def generate(
        self,
        profile: CandidateProfile,
        job: JobPosting,
        match: Optional[MatchResult] = None,
        tone: str = "professional",
    ) -> str:
        """Generate a cover letter using the LLM, falling back to a template."""
        prompt = self._build_prompt(profile, job, match)

        # Try Claude API first
        letter = self._call_claude(prompt, tone)
        if letter:
            return letter

        # Fallback to GPT-4
        letter = self._call_openai(prompt, tone)
        if letter:
            return letter

        # Final fallback: template-based generation
        logger.info("No LLM available — using template-based cover letter")
        return self._template_fallback(profile, job, match)

    def _call_claude(self, prompt: str, tone: str) -> Optional[str]:
        """Call Anthropic's Claude API."""
        api_key = settings.claude_api_key
        if not api_key:
            logger.debug("No CLAUDE_API_KEY set — skipping Claude")
            return None

        try:
            import httpx

            system_msg = COVER_LETTER_SYSTEM_PROMPT + (
                f"\n\nTone: {tone}. Write in a {tone} style — "
                "professional = formal and corporate; "
                "startup = energetic and direct; "
                "creative = expressive and distinctive."
            )

            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "system": system_msg,
                    "messages": [
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", [])
            for block in content:
                if block.get("type") == "text":
                    return block["text"].strip()
        except Exception as e:
            logger.warning("Claude API call failed: %s", e)

        return None

    def _call_openai(self, prompt: str, tone: str) -> Optional[str]:
        """Call OpenAI's GPT-4 API as fallback."""
        api_key = settings.openai_api_key
        if not api_key:
            logger.debug("No OPENAI_API_KEY set — skipping OpenAI")
            return None

        try:
            import httpx

            system_msg = COVER_LETTER_SYSTEM_PROMPT + (
                f"\n\nTone: {tone}."
            )

            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                },
                json={
                    "model": "gpt-4",
                    "max_tokens": 1024,
                    "temperature": 0.7,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning("OpenAI API call failed: %s", e)

        return None

    def _template_fallback(
        self,
        profile: CandidateProfile,
        job: JobPosting,
        match: Optional[MatchResult] = None,
    ) -> str:
        """Generate a basic cover letter from a Jinja2 or built-in template."""
        name = profile.full_name or "The Candidate"
        title = profile.experiences[0].title if profile.experiences else "professional"
        skills = ", ".join(profile.skill_names[:8])

        # Skill overlap
        overlap = match.skill_overlap[:5] if match and match.skill_overlap else []

        letter = f"""Dear Hiring Manager,

I am writing to express my strong interest in the {job.title} position at {job.company}. \
As a {title} with {profile.years_of_experience:.0f} years of experience, \
I am confident that my background aligns well with the requirements of this role.

{self._write_highlight(profile, job, overlap)}

My technical skill set includes {skills}, which I believe would allow me \
to contribute effectively to the {job.company} team from day one.

I would welcome the opportunity to discuss how my experience and enthusiasm \
can benefit {job.company}. Thank you for your time and consideration.

Sincerely,
{name}"""
        return letter

    def _write_highlight(self, profile: CandidateProfile, job: JobPosting, overlap: list[str]) -> str:
        """Generate a short highlight paragraph from available data."""
        if overlap:
            skills_str = ", ".join(overlap[:5])
            return (
                f"In my current role, I have developed strong capabilities in {skills_str}, "
                f"which are directly relevant to this position. "
                f"I am particularly excited about the opportunity to bring these skills to {job.company}."
            )

        # Fallback if no overlap
        if profile.experiences:
            exp = profile.experiences[0]
            return (
                f"During my time at {exp.company}, I honed my skills as a {exp.title}, "
                f"delivering impactful results that I am eager to replicate at {job.company}."
            )

        return (
            f"I have been following {job.company}'s work with great interest, "
            f"and I am excited about the opportunity to contribute to your team."
        )

    def generate_and_save(
        self,
        profile: CandidateProfile,
        job: JobPosting,
        match: Optional[MatchResult] = None,
        tone: str = "professional",
        output_dir: Optional[Path] = None,
    ) -> Path:
        """Generate a cover letter and save it to a file."""
        letter = self.generate(profile, job, match, tone)

        output_dir = output_dir or settings.cover_letter_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create a safe filename
        safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", f"{job.company}_{job.title}".lower())
        safe_name = safe_name.strip("_")[:60]
        output_path = output_dir / f"{safe_name}.txt"

        output_path.write_text(letter, encoding="utf-8")
        logger.info("Cover letter saved: %s", output_path)
        return output_path
