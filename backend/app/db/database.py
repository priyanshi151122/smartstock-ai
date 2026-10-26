"""Thin, engine-agnostic database abstraction.

The application deliberately avoids an ORM. SQL statements are written once using
the ``?`` placeholder style and this module translates them for the active driver:

* ``sqlite:///relative/or/absolute/path.db``  -> standard library ``sqlite3``
* ``postgresql://user:pass@host/db``          -> ``psycopg`` (optional dependency)

Swapping the backend therefore only requires changing ``DATABASE_URL`` plus
installing the PostgreSQL driver. Every statement in the application is
parameterised; no user supplied value is ever interpolated into SQL text.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
MIGRATIONS_DIR = Path(__file__).with_name("migrations")


class DatabaseError(RuntimeError):
    """Raised when the database driver cannot be initialised."""


def split_statements(sql: str) -> list[str]:
    """Split a SQL script into statements, ignoring ``--`` comments.

    Naively splitting on ``;`` breaks when a comment contains a semicolon, which is
    exactly the kind of file a hand-written migration is.
    """
    without_comments = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    return [statement.strip() for statement in without_comments.split(";") if statement.strip()]


def _rewrite_placeholders(sql: str) -> str:
    """Convert ``?`` placeholders to ``%s`` for the PostgreSQL driver."""
    return sql.replace("?", "%s")


class Database:
    """Small connection manager shared by every repository."""

    def __init__(self, url: str) -> None:
        self.url = url
        self._lock = threading.Lock()
        self.dialect, self._connect_kwargs = self._parse_url(url)

    # ------------------------------------------------------------------ parsing
    @staticmethod
    def _parse_url(url: str) -> tuple[str, dict[str, Any]]:
        if url.startswith("sqlite:///"):
            raw = url.removeprefix("sqlite:///")
            if raw in {"", ":memory:"}:
                return "sqlite", {"database": ":memory:"}
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            return "sqlite", {"database": str(path)}
        if url.startswith(("postgresql://", "postgres://")):
            return "postgres", {"dsn": url}
        raise DatabaseError(
            f"Unsupported DATABASE_URL scheme. Use sqlite:///path.db or postgresql://..."
        )

    # --------------------------------------------------------------- connections
    @contextmanager
    def connect(self) -> Iterator[Any]:
        """Yield a raw DB-API connection (autocommit disabled, rows as dicts)."""
        if self.dialect == "sqlite":
            conn = sqlite3.connect(self._connect_kwargs["database"], timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
        else:  # pragma: no cover - exercised only with a PostgreSQL DSN
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:  # pragma: no cover
                raise DatabaseError(
                    "PostgreSQL support requires the 'psycopg[binary]' package. "
                    "Install it or switch DATABASE_URL to sqlite:///."
                ) from exc
            conn = psycopg.connect(self._connect_kwargs["dsn"], row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _prepare(self, sql: str) -> str:
        return _rewrite_placeholders(sql) if self.dialect == "postgres" else sql

    # ------------------------------------------------------------------ helpers
    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        with self._lock, self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(self._prepare(sql), tuple(params or ()))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def query_one(self, sql: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Sequence[Any] | None = None, default: Any = None) -> Any:
        row = self.query_one(sql, params)
        if not row:
            return default
        value = next(iter(row.values()))
        return default if value is None else value

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        """Run a write statement and return the last inserted row id (or rowcount)."""
        with self._lock, self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(self._prepare(sql), tuple(params or ()))
            return cursor.lastrowid if cursor.lastrowid else cursor.rowcount

    def execute_many(self, sql: str, rows: Sequence[Sequence[Any]]) -> int:
        if not rows:
            return 0
        with self._lock, self.connect() as conn:
            cursor = conn.cursor()
            cursor.executemany(self._prepare(sql), rows)
            return cursor.rowcount

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Yield a cursor inside a single transaction for multi-statement writes."""
        with self._lock, self.connect() as conn:
            cursor = conn.cursor()
            yield cursor

    # ------------------------------------------------------------------- schema
    def initialise_schema(self) -> None:
        """Create tables if absent and apply incremental migrations (idempotent)."""
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        statements = split_statements(schema_sql)
        with self._lock, self.connect() as conn:
            cursor = conn.cursor()
            for statement in statements:
                cursor.execute(self._prepare(statement))
        self._apply_migrations()

    def _apply_migrations(self) -> None:
        """Apply additive .sql migration files once, tracked in schema_migrations."""
        if not MIGRATIONS_DIR.exists():
            return
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            row["filename"]
            for row in self.query("SELECT filename FROM schema_migrations")
        }
        from datetime import datetime, timezone

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            with self.transaction() as cursor:
                for statement in split_statements(sql):
                    cursor.execute(self._prepare(statement))
                cursor.execute(
                    self._prepare(
                        "INSERT INTO schema_migrations (filename, applied_at) VALUES (?, ?)"
                    ),
                    (path.name, datetime.now(timezone.utc).isoformat()),
                )

    def table_names(self) -> list[str]:
        rows = self.query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [row["name"] for row in rows]

    def is_sqlite(self) -> bool:
        return self.dialect == "sqlite"


_SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def assert_identifier(name: str) -> str:
    """Guard for the rare case where an identifier must be interpolated (sorting)."""
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name
