"""
JSON-file-based storage implementation — used as fallback when PostgreSQL
is unavailable.  Mirrors the StorageBackend interface so API endpoints work
without a running database.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Optional

from backend.database import storage as json_storage
from backend.storage.backend import AppStats, SourceBreakdown, StorageBackend

logger = logging.getLogger(__name__)


class JsonBackend(StorageBackend):
    """Storage backend backed by JSON files (via the existing JSONStorage singleton)."""

    async def is_available(self) -> bool:
        return True

    # ─── Internal helpers ───────────────────────────────────────────────────

    def _get_data(self) -> dict[str, Any]:
        """Access the full data dict (JSONStorage stores it as _data)."""
        return json_storage._data  # type: ignore[attr-defined]

    def _save(self) -> None:
        json_storage._save()  # type: ignore[attr-defined]

    # ─── Profiles ───────────────────────────────────────────────────────────

    async def list_profiles(self) -> list[dict[str, Any]]:
        return list(reversed(json_storage.get_profiles()))  # newest first

    async def get_profile(self, profile_id: str) -> Optional[dict[str, Any]]:
        for p in json_storage.get_profiles():
            if p.get("id") == profile_id:
                return p
        return None

    async def create_profile(self, data: dict[str, Any]) -> str:
        import uuid
        profile_id = data.get("id") or str(uuid.uuid4())
        data["id"] = profile_id
        data["parsed_at"] = datetime.now(UTC).isoformat()
        json_storage.save_profile(data)
        return profile_id

    async def delete_profile(self, profile_id: str) -> bool:
        data = self._get_data()
        profiles = data.get("profiles", [])
        filtered = [p for p in profiles if p.get("id") != profile_id]
        if len(filtered) == len(profiles):
            return False
        data["profiles"] = filtered
        self._save()
        return True

    # ─── Jobs ───────────────────────────────────────────────────────────────

    async def list_jobs(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        jobs = list(reversed(json_storage.get_jobs()))  # newest first
        return jobs[offset:offset + limit]

    async def store_jobs(self, jobs: list[dict[str, Any]]) -> int:
        data = self._get_data()
        existing = data.get("jobs", [])
        existing.extend(jobs)
        data["jobs"] = existing
        self._save()
        return len(jobs)

    async def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        for j in json_storage.get_jobs():
            if j.get("id") == job_id:
                return j
        return None

    async def delete_job(self, job_id: str) -> bool:
        data = self._get_data()
        jobs = data.get("jobs", [])
        filtered = [j for j in jobs if j.get("id") != job_id]
        if len(filtered) == len(jobs):
            return False
        data["jobs"] = filtered
        self._save()
        return True

    async def count_jobs_by_source(self) -> list[SourceBreakdown]:
        sources = Counter(j.get("source", "unknown") for j in json_storage.get_jobs())
        return [SourceBreakdown(source=s, count=c) for s, c in sources.most_common()]

    # ─── Applications ───────────────────────────────────────────────────────

    async def list_applications(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        apps = list(reversed(json_storage.get_applications()))  # newest first
        if status:
            apps = [a for a in apps if a.get("status") == status]
        if profile_id:
            apps = [a for a in apps if a.get("profile_id") == profile_id]
        # Enrich with job data (use copies to avoid mutating stored data)
        enriched = []
        for a in apps:
            entry = dict(a)
            self._enrich_with_job_data(entry, a)
            enriched.append(entry)
        return enriched[offset:offset + limit]

    async def get_application(self, app_id: str) -> Optional[dict[str, Any]]:
        apps = json_storage.get_applications()
        app = next((a for a in apps if a.get("id") == app_id), None)
        if not app:
            return None
        # Return a copy enriched with job data (don't mutate stored data)
        entry = dict(app)
        self._enrich_with_job_data(entry, app)
        return entry

    @staticmethod
    def _enrich_with_job_data(entry: dict[str, Any], raw: dict[str, Any]) -> None:
        """Mutate entry in-place to add job_title, company, match_score."""
        # Try nested 'job' dict (CLI match command format)
        job_data = raw.get("job")
        if isinstance(job_data, dict):
            entry.setdefault("job_title", job_data.get("title", ""))
            entry.setdefault("company", job_data.get("company", ""))
            if not entry.get("match_score") and raw.get("score") is not None:
                entry["match_score"] = raw["score"]

        # Then try job_id lookup against stored jobs
        job_id = raw.get("job_id")
        if job_id and (not entry.get("job_title") or not entry.get("company")):
            job = next(
                (j for j in json_storage.get_jobs() if j.get("id") == job_id),
                None,
            )
            if job:
                if not entry.get("job_title"):
                    entry["job_title"] = job.get("title", "")
                if not entry.get("company"):
                    entry["company"] = job.get("company", "")

    async def create_application(self, data: dict[str, Any]) -> str:
        import uuid
        app_id = str(uuid.uuid4())
        data["id"] = app_id
        data["created_at"] = datetime.now(UTC).isoformat()
        json_storage.save_application(data)
        return app_id

    async def update_application_status(self, app_id: str, status: str) -> bool:
        data = self._get_data()
        apps = data.get("applications", [])
        for a in apps:
            if a.get("id") == app_id:
                a["status"] = status
                if status == "submitted" and not a.get("submitted_at"):
                    a["submitted_at"] = datetime.now(UTC).isoformat()
                self._save()
                return True
        return False

    async def delete_application(self, app_id: str) -> bool:
        data = self._get_data()
        apps = data.get("applications", [])
        filtered = [a for a in apps if a.get("id") != app_id]
        if len(filtered) == len(apps):
            return False
        data["applications"] = filtered
        self._save()
        return True

    async def count_applications_by_status(self) -> dict[str, int]:
        statuses = Counter(a.get("status", "pending") for a in json_storage.get_applications())
        return dict(statuses)

    # ─── Dashboard Aggregates ───────────────────────────────────────────────

    async def get_stats(self) -> AppStats:
        profiles = json_storage.get_profiles()
        jobs = json_storage.get_jobs()
        apps = json_storage.get_applications()

        submitted = sum(1 for a in apps if a.get("status") == "submitted")
        # Support both 'match_score' and legacy 'score' key
        scores = []
        for a in apps:
            ms = a.get("match_score") or a.get("score")
            if ms is not None:
                scores.append(float(ms))
        avg_score = sum(scores) / len(scores) if scores else 0.0

        today = datetime.now(UTC).date()
        today_count = sum(
            1 for a in apps
            if a.get("created_at") and datetime.fromisoformat(a["created_at"]).date() == today
        )

        return AppStats(
            total_profiles=len(profiles),
            total_jobs=len(jobs),
            total_applications=len(apps),
            submitted_applications=submitted,
            avg_match_score=avg_score,
            applications_today=today_count,
            database_connected=False,
        )
