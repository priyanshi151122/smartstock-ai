"""Append-only audit trail for anything that mutates operational state."""

from __future__ import annotations

from typing import Any

from app.db import Database
from app.utils import json_dumps, json_loads, sanitize_text, utcnow_iso


def log(
    db: Database,
    *,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    actor: str = "system",
    details: dict[str, Any] | None = None,
) -> int:
    return int(
        db.execute(
            """
            INSERT INTO audit_logs (created_at, actor, action, entity_type, entity_id, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                utcnow_iso(),
                sanitize_text(actor, 80) or "system",
                sanitize_text(action, 80) or "unknown",
                sanitize_text(entity_type, 60) or "unknown",
                None if entity_id is None else str(entity_id),
                json_dumps(details or {}),
            ),
        )
    )


def list_logs(
    db: Database,
    *,
    limit: int = 100,
    offset: int = 0,
    entity_type: str | None = None,
    action: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    clauses, params = ["1 = 1"], []
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if action:
        clauses.append("action = ?")
        params.append(action)
    where = " WHERE " + " AND ".join(clauses)
    total = int(db.scalar(f"SELECT COUNT(*) AS c FROM audit_logs{where}", params, 0) or 0)
    rows = db.query(
        f"SELECT * FROM audit_logs{where} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [int(limit), int(offset)],
    )
    for row in rows:
        row["details"] = json_loads(row.get("details"), {})
    return rows, total
