"""
Semantic Matching Engine — scores jobs against a candidate profile.

Scoring formula (composite):
  - 40% Vector cosine similarity (semantic fit)
  - 40% Skill overlap ratio (keyword fit)
  - 10% Seniority alignment
  - 10% Location / remote preference

Each component is normalised to [0, 1]; the composite score is also [0, 1].
Jobs scoring above MATCH_THRESHOLD are forwarded to the apply stage.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from backend.config import settings
from backend.models.profile import (
    CandidateProfile,
    JobPosting,
    MatchResult,
    SeniorityLevel,
)

logger = logging.getLogger(__name__)

# ─── Seniority proximity matrix ─────────────────────────────────────────────
# Ordered list for numerical comparison
SENIORITY_ORDER = [
    SeniorityLevel.ENTRY,
    SeniorityLevel.JUNIOR,
    SeniorityLevel.MID,
    SeniorityLevel.SENIOR,
    SeniorityLevel.STAFF,
    SeniorityLevel.PRINCIPAL,
    SeniorityLevel.EXECUTIVE,
]

# Maximum allowed distance in seniority levels
MAX_SENIORITY_DISTANCE = 2


class SemanticMatcher:
    """Composite scorer that combines vector, skill, seniority, and location signals."""

    def __init__(self, threshold: float | None = None):
        self.threshold = threshold if threshold is not None else settings.match_threshold
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            from backend.services.embedding import EmbeddingService
            self._embedder = EmbeddingService()
            self._embedder.initialize()
        return self._embedder

    # ─── Scoring components ──────────────────────────────────────────────────

    def _vector_score(self, profile: CandidateProfile, job: JobPosting) -> float:
        """Cosine-similarity based score between CV and job description, in [0, 1]."""
        try:
            # Embed the profile text and job text, then compute cosine similarity
            from sentence_transformers.util import cos_sim
            import torch

            cv_emb = torch.tensor(self.embedder.embed(profile.raw_text))
            job_emb = torch.tensor(self.embedder.embed(job.description))

            sim = cos_sim(cv_emb.unsqueeze(0), job_emb.unsqueeze(0)).item()
            # cos_sim is [-1, 1]; clamp to [0, 1]
            return max(0.0, min(1.0, (sim + 1) / 2))
        except Exception as e:
            logger.debug("Vector scoring failed: %s", e)
            return 0.5  # neutral fallback

    def _skill_score(self, profile: CandidateProfile, job: JobPosting) -> tuple[float, list[str], list[str]]:
        """Skill overlap ratio in [0, 1], plus the overlap and gap lists."""
        cv_skills = set(s.lower() for s in profile.skill_names)
        job_skills = set(s.lower() for s in job.skills_required)

        if not job_skills:
            return 0.5, [], []

        overlap = cv_skills & job_skills
        gap = job_skills - cv_skills
        ratio = len(overlap) / len(job_skills)
        return ratio, sorted(overlap), sorted(gap)

    def _seniority_score(self, profile: CandidateProfile, job: JobPosting) -> tuple[float, bool]:
        """1.0 if within MAX_SENIORITY_DISTANCE, 0.0 otherwise."""
        try:
            cv_idx = SENIORITY_ORDER.index(profile.seniority)
        except ValueError:
            return 0.5, False

        try:
            job_idx = SENIORITY_ORDER.index(job.seniority)
        except ValueError:
            return 0.5, False

        distance = abs(cv_idx - job_idx)
        if distance == 0:
            return 1.0, True
        elif distance <= 1:
            return 0.8, True
        elif distance <= MAX_SENIORITY_DISTANCE:
            return 0.5, True
        return 0.0, False

    def _location_score(self, profile: CandidateProfile, job: JobPosting) -> float:
        """1.0 if remote is preferred and job is remote, or location matches."""
        if profile.remote_preferred and job.remote:
            return 1.0

        if not profile.preferred_locations or not job.location:
            return 0.5  # neutral — no preference stated

        cv_locs = [loc.lower().strip() for loc in profile.preferred_locations]
        job_loc = job.location.lower().strip()

        # Check for any match (city, state, country, or "remote")
        for cl in cv_locs:
            if cl in job_loc or job_loc in cl:
                return 1.0
            # Remote keyword match
            if cl == "remote" and job.remote:
                return 1.0

        return 0.2  # low score — no location match

    # ─── Public API ──────────────────────────────────────────────────────────

    def score(self, profile: CandidateProfile, job: JobPosting) -> MatchResult:
        """Compute a composite MatchResult for one profile–job pair."""
        v_score = self._vector_score(profile, job)
        s_score, overlap, gap = self._skill_score(profile, job)
        se_score, se_match = self._seniority_score(profile, job)
        l_score = self._location_score(profile, job)

        composite = (
            0.40 * v_score +
            0.40 * s_score +
            0.10 * se_score +
            0.10 * l_score
        )

        reasoning_parts = []
        reasoning_parts.append(f"Vector similarity: {v_score:.0%}")
        reasoning_parts.append(f"Skill overlap: {s_score:.0%} ({len(overlap)} matched, {len(gap)} gaps)")
        reasoning_parts.append(f"Seniority: {'match' if se_match else 'mismatch'} ({se_score:.0%})")
        reasoning_parts.append(f"Location: {l_score:.0%}")

        return MatchResult(
            job=job,
            score=round(min(1.0, composite), 4),
            skill_overlap=overlap,
            skill_gaps=gap,
            seniority_match=se_match,
            location_match=l_score >= 0.5,
            passed_threshold=composite >= self.threshold,
            reasoning=" | ".join(reasoning_parts),
        )

    def rank(
        self,
        profile: CandidateProfile,
        jobs: list[JobPosting],
        top_k: int = 20,
    ) -> list[MatchResult]:
        """Score all jobs against the profile and return a ranked list."""
        results = [self.score(profile, job) for job in jobs]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def shortlist(self, results: list[MatchResult]) -> list[MatchResult]:
        """Filter results to only those that passed the threshold."""
        return [r for r in results if r.passed_threshold]
