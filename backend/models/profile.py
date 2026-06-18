"""
Pydantic models for the job application agent's core data types.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SeniorityLevel(str, Enum):
    """Estimated seniority level based on years of experience and role title."""

    ENTRY = "entry"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    EXECUTIVE = "executive"
    UNKNOWN = "unknown"


class ApplicationStatus(str, Enum):
    """State machine for tracking application progress."""

    PENDING = "pending"
    MATCHED = "matched"
    APPLIED = "applied"
    UNDER_REVIEW = "under_review"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    CLOSED = "closed"
    SKIPPED = "skipped"
    ERROR = "error"


class Education(BaseModel):
    """A single education entry on a CV."""

    institution: str = Field("", description="School or university name")
    degree: str = Field("", description="Degree or certification name")
    field: str = Field("", description="Field of study / major")
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    gpa: Optional[str] = None


class Experience(BaseModel):
    """A single work experience entry on a CV."""

    company: str = Field("", description="Employer name")
    title: str = Field("", description="Job title")
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    description: str = Field("", description="Bullet points / summary of role")
    skills_used: list[str] = Field(default_factory=list)
    years_at_role: Optional[float] = None


class Skill(BaseModel):
    """A detected skill with confidence and category."""

    name: str = Field(description="Skill name")
    category: str = Field("general", description="e.g. language, framework, tool, soft")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    mentions: int = Field(default=1, description="How many times it appeared in the CV")


class JobPosting(BaseModel):
    """A job posting from a discovery source."""

    id: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    source: str = ""  # linkedin, indeed, glassdoor, etc.
    salary_range: Optional[str] = None
    remote: bool = False
    posted_date: Optional[str] = None
    skills_required: list[str] = Field(default_factory=list)
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN


class CandidateProfile(BaseModel):
    """Full parsed candidate profile extracted from CV and user input."""

    raw_text: str = Field("", description="Full raw text extracted from CV")
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""

    skills: list[Skill] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)

    years_of_experience: float = 0.0
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    remote_preferred: bool = False

    persona: Optional[Persona] = None

    embedding: Optional[list[float]] = None
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_file: str = ""

    @property
    def skill_names(self) -> list[str]:
        return [s.name for s in self.skills]

    def summary(self) -> dict:
        """Return a compact summary suitable for LLM context or display."""
        return {
            "name": self.full_name,
            "title": self.experiences[0].title if self.experiences else "N/A",
            "years_exp": self.years_of_experience,
            "seniority": self.seniority.value,
            "skills": self.skill_names[:20],
            "recent_roles": [
                f"{e.title} @ {e.company}" for e in self.experiences[:3]
            ],
        }


class Persona(BaseModel):
    """AI persona — the candidate's voice, style, and canned screening answers."""

    communication_style: str = "professional"
    key_messages: list[str] = Field(default_factory=list)
    screening_answers: dict[str, str] = Field(default_factory=dict)
    tone_description: str = ""
    voice_sample: str = ""
    onboarded: bool = False


class MatchResult(BaseModel):
    """Result of matching a candidate profile against a job posting."""

    job: JobPosting
    score: float = Field(ge=0.0, le=1.0)
    skill_overlap: list[str] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    seniority_match: bool = False
    location_match: bool = False
    passed_threshold: bool = False
    reasoning: str = ""


class ApplicationRecord(BaseModel):
    """Full record of one submitted application."""

    id: str = ""
    job: JobPosting = Field(default_factory=JobPosting)
    match_score: float = 0.0
    status: ApplicationStatus = ApplicationStatus.PENDING
    cover_letter_path: Optional[str] = None
    submitted_at: Optional[datetime] = None
    response_received_at: Optional[datetime] = None
    notes: str = ""
    error_log: str = ""
