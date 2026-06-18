"""Storage abstraction layer — unifies PostgreSQL and JSON backends."""

from __future__ import annotations

from backend.storage.backend import StorageBackend
from backend.storage.json_backend import JsonBackend
from backend.storage.postgres_backend import PostgresBackend

__all__ = ["StorageBackend", "PostgresBackend", "JsonBackend"]
