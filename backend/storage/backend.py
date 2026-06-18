"""
Abstract base class for storage backends.

Defines the repository interface used by both the FastAPI dashboard API
and the CLI tool so they can share a common storage contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class AppStats:
    """Aggregated dashboard statistics."""
    total_profiles: int = 0
    total_jobs: int = 0
    total_applications: int = 0
    submitted_applications: int = 0
    avg_match_score: float = 0.0
    applications_today: int = 0
    database_connected: bool = False


@dataclass
class SourceBreakdown:
    """Job count grouped by discovery source."""
    source: str
    count: int


class StorageBackend(ABC):
    """Abstract repository for all persistent storage operations."""

    # ─── Profiles ───────────────────────────────────────────────────────────

    @abstractmethod
    async def list_profiles(self) -> list[dict[str, Any]]:
        """Return all profiles, newest first."""
        ...

    @abstractmethod
    async def get_profile(self, profile_id: str) -> Optional[dict[str, Any]]:
        """Return a single profile by ID, or None."""
        ...

    @abstractmethod
    async def create_profile(self, data: dict[str, Any]) -> str:
        """Persist a new profile and return its ID."""
        ...

    @abstractmethod
    async def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile (and cascade applications). Return True if deleted."""
        ...

    # ─── Jobs ───────────────────────────────────────────────────────────────

    @abstractmethod
    async def list_jobs(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Return stored job postings."""
        ...

    @abstractmethod
    async def store_jobs(self, jobs: list[dict[str, Any]]) -> int:
        """Store a batch of jobs. Return count stored."""
        ...

    @abstractmethod
    async def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        """Return a single job by ID, or None."""
        ...

    @abstractmethod
    async def delete_job(self, job_id: str) -> bool:
        """Delete a job posting. Return True if deleted."""
        ...

    @abstractmethod
    async def count_jobs_by_source(self) -> list[SourceBreakdown]:
        """Return job counts grouped by source."""
        ...

    # ─── Applications ───────────────────────────────────────────────────────

    @abstractmethod
    async def list_applications(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return application records with joined job data (title + company)."""
        ...

    @abstractmethod
    async def get_application(self, app_id: str) -> Optional[dict[str, Any]]:
        """Return a single application by ID with joined job data, or None."""
        ...

    @abstractmethod
    async def create_application(self, data: dict[str, Any]) -> str:
        """Persist a new application record and return its ID."""
        ...

    @abstractmethod
    async def update_application_status(self, app_id: str, status: str) -> bool:
        """Update the status of an application. Return True if updated."""
        ...

    @abstractmethod
    async def delete_application(self, app_id: str) -> bool:
        """Delete an application record. Return True if deleted."""
        ...

    @abstractmethod
    async def count_applications_by_status(self) -> dict[str, int]:
        """Return application counts grouped by status."""
        ...

    # ─── Dashboard Aggregates ───────────────────────────────────────────────

    @abstractmethod
    async def get_stats(self) -> AppStats:
        """Return aggregated dashboard statistics."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Return True if the backend is reachable."""
        ...
