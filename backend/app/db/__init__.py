"""Database package: engine-agnostic access layer."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings

from .database import Database, DatabaseError, assert_identifier

__all__ = [
    "Database",
    "DatabaseError",
    "assert_identifier",
    "get_database",
    "get_db",
    "reset_database_cache",
]


@lru_cache(maxsize=1)
def get_database() -> Database:
    """Process-wide database handle. Schema is created on first use."""
    database = Database(get_settings().database_url)
    database.initialise_schema()
    return database


def get_db() -> Database:
    """FastAPI dependency. Override in tests with app.dependency_overrides."""
    return get_database()


def reset_database_cache() -> None:
    """Drop the cached handle (used by tests that switch DATABASE_URL)."""
    get_database.cache_clear()
