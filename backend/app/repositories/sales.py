"""Sales records: filtered aggregation queries plus import batch bookkeeping."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.db import Database
from app.utils import json_dumps, json_loads, sanitize_text, utcnow_iso

BASE_FROM = """
FROM sales_records s
JOIN products p ON p.id = s.product_id
"""


def build_filters(
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    category: str | None = None,
    product_id: int | None = None,
    data_source: str | None = None,
) -> tuple[str, list[Any]]:
    """Return a parameterised WHERE clause (always starts with ``WHERE 1 = 1``)."""
    clauses, params = ["1 = 1"], []
    if start_date:
        clauses.append("s.sale_date >= ?")
        params.append(str(start_date))
    if end_date:
        clauses.append("s.sale_date <= ?")
        params.append(str(end_date))
    if category:
        clauses.append("p.category = ?")
        params.append(category)
    if product_id:
        clauses.append("s.product_id = ?")
        params.append(int(product_id))
    if data_source == "demo":
        clauses.append("s.is_demo = 1")
    elif data_source == "actual":
        clauses.append("s.is_demo = 0")
    return "WHERE " + " AND ".join(clauses), params


def totals(db: Database, **filters: Any) -> dict[str, Any]:
    where, params = build_filters(**filters)
    row = db.query_one(
        f"""
        SELECT COALESCE(SUM(s.revenue), 0)                AS revenue,
               COALESCE(SUM(s.quantity), 0)               AS units,
               COUNT(*)                                   AS rows,
               COUNT(DISTINCT s.product_id)               AS products,
               COUNT(DISTINCT s.order_id)                 AS orders,
               COUNT(DISTINCT s.sale_date)                AS active_days,
               MIN(s.sale_date)                           AS first_date,
               MAX(s.sale_date)                           AS last_date,
               SUM(CASE WHEN s.is_demo = 1 THEN 1 ELSE 0 END) AS demo_rows
        {BASE_FROM}
        {where}
        """,
        params,
    )
    return row or {}


def time_series(
    db: Database,
    *,
    granularity: str = "day",
    **filters: Any,
) -> list[dict[str, Any]]:
    where, params = build_filters(**filters)
    if granularity == "week":
        period = "strftime('%Y-W%W', s.sale_date)"
    elif granularity == "month":
        period = "strftime('%Y-%m', s.sale_date)"
    else:
        period = "s.sale_date"
    return db.query(
        f"""
        SELECT {period} AS period,
               COALESCE(SUM(s.revenue), 0) AS revenue,
               COALESCE(SUM(s.quantity), 0) AS units,
               COUNT(DISTINCT s.order_id) AS orders
        {BASE_FROM}
        {where}
        GROUP BY period
        ORDER BY period
        """,
        params,
    )


def by_category(db: Database, **filters: Any) -> list[dict[str, Any]]:
    where, params = build_filters(**filters)
    return db.query(
        f"""
        SELECT COALESCE(p.category, 'Uncategorised') AS category,
               COALESCE(SUM(s.revenue), 0) AS revenue,
               COALESCE(SUM(s.quantity), 0) AS units
        {BASE_FROM}
        {where}
        GROUP BY category
        ORDER BY revenue DESC
        """,
        params,
    )


def by_product(
    db: Database,
    *,
    limit: int | None = None,
    order_by: str = "revenue",
    ascending: bool = False,
    **filters: Any,
) -> list[dict[str, Any]]:
    where, params = build_filters(**filters)
    order_column = {
        "revenue": "revenue",
        "units": "units",
        "name": "p.name",
        "orders": "orders",
    }.get(order_by, "revenue")
    direction = "ASC" if ascending else "DESC"
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    return db.query(
        f"""
        SELECT p.id AS product_id,
               p.sku,
               p.name,
               p.category,
               COALESCE(p.unit_cost, NULL) AS unit_cost,
               COALESCE(p.selling_price, NULL) AS selling_price,
               COALESCE(SUM(s.revenue), 0) AS revenue,
               COALESCE(SUM(s.quantity), 0) AS units,
               COUNT(DISTINCT s.order_id) AS orders,
               COUNT(*) AS rows,
               MAX(s.sale_date) AS last_sale_date,
               CASE WHEN SUM(s.quantity) > 0
                    THEN SUM(s.revenue) / SUM(s.quantity) END AS avg_price
        {BASE_FROM}
        {where}
        GROUP BY p.id, p.sku, p.name, p.category, p.unit_cost, p.selling_price
        ORDER BY {order_column} {direction}, p.name ASC
        {limit_sql}
        """,
        params,
    )


def daily_demand(db: Database, product_id: int, **filters: Any) -> list[dict[str, Any]]:
    where, params = build_filters(product_id=product_id, **filters)
    return db.query(
        f"""
        SELECT s.sale_date AS date, COALESCE(SUM(s.quantity), 0) AS units
        {BASE_FROM}
        {where}
        GROUP BY s.sale_date
        ORDER BY s.sale_date
        """,
        params,
    )


def distinct_dates(db: Database) -> tuple[str | None, str | None]:
    row = db.query_one("SELECT MIN(sale_date) AS start, MAX(sale_date) AS end FROM sales_records")
    if not row:
        return None, None
    return row.get("start"), row.get("end")


def recent_demand_by_product(
    db: Database, *, days: int = 28, data_source: str | None = None
) -> dict[int, dict[str, float]]:
    """Trailing demand per product, used for inventory risk without a forecast."""
    end = date.today()
    from datetime import timedelta

    start = end - timedelta(days=days - 1)
    where, params = build_filters(start_date=start, end_date=end, data_source=data_source)
    rows = db.query(
        f"""
        SELECT s.product_id,
               COALESCE(SUM(s.quantity), 0) AS units,
               COUNT(DISTINCT s.sale_date) AS active_days
        {BASE_FROM}
        {where}
        GROUP BY s.product_id
        """,
        params,
    )
    result: dict[int, dict[str, float]] = {}
    for row in rows:
        result[int(row["product_id"])] = {
            "units": float(row["units"] or 0),
            "daily_avg": float(row["units"] or 0) / days,
            "active_days": float(row["active_days"] or 0),
        }
    return result


def demand_stats(
    db: Database, *, start_date: date | str | None = None, end_date: date | str | None = None,
    data_source: str | None = None
) -> dict[int, dict[str, Any]]:
    """Per-product daily demand mean/stddev computed in Python (driver agnostic)."""
    where, params = build_filters(start_date=start_date, end_date=end_date, data_source=data_source)
    rows = db.query(
        f"""
        SELECT s.product_id, s.sale_date, SUM(s.quantity) AS units
        {BASE_FROM}
        {where}
        GROUP BY s.product_id, s.sale_date
        ORDER BY s.product_id, s.sale_date
        """,
        params,
    )
    grouped: dict[int, list[float]] = {}
    for row in rows:
        grouped.setdefault(int(row["product_id"]), []).append(float(row["units"] or 0))
    stats: dict[int, dict[str, Any]] = {}
    for product_id, values in grouped.items():
        n = len(values)
        mean = sum(values) / n if n else 0.0
        variance = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
        stats[product_id] = {
            "mean": mean,
            "std": variance ** 0.5,
            "active_days": n,
            "total": sum(values),
            "cv": (variance ** 0.5 / mean) if mean else None,
        }
    return stats


# ------------------------------------------------------------------ import batch
def create_import_batch(
    db: Database,
    *,
    filename: str,
    file_type: str,
    file_size_bytes: int,
    status: str = "validated",
    data_source: str = "actual",
    column_mapping: dict[str, Any] | None = None,
    message: str | None = None,
) -> int:
    return int(
        db.execute(
            """
            INSERT INTO import_batches (filename, file_type, file_size_bytes, status, data_source,
                                        column_mapping, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sanitize_text(filename, 200) or "upload",
                file_type,
                int(file_size_bytes),
                status,
                data_source,
                json_dumps(column_mapping or {}),
                sanitize_text(message, 400),
                utcnow_iso(),
            ),
        )
    )


def update_import_batch(db: Database, batch_id: int, fields: dict[str, Any]) -> None:
    allowed = {
        "status",
        "data_source",
        "total_rows",
        "valid_rows",
        "invalid_rows",
        "duplicate_rows",
        "imported_rows",
        "column_mapping",
        "validation_summary",
        "issues",
        "cleaning_applied",
        "message",
        "completed_at",
    }
    updates = {}
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        updates[key] = json_dumps(value) if isinstance(value, (dict, list)) else value
    if not updates:
        return
    assignments = ", ".join(f"{column} = ?" for column in updates)
    db.execute(
        f"UPDATE import_batches SET {assignments} WHERE id = ?",
        list(updates.values()) + [batch_id],
    )


def get_import_batch(db: Database, batch_id: int) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM import_batches WHERE id = ?", (batch_id,))
    if not row:
        return None
    row["column_mapping"] = json_loads(row.get("column_mapping"), {})
    row["validation_summary"] = json_loads(row.get("validation_summary"), {})
    row["issues"] = json_loads(row.get("issues"), [])
    row["cleaning_applied"] = json_loads(row.get("cleaning_applied"), [])
    return row


def list_import_batches(db: Database, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT * FROM import_batches ORDER BY id DESC LIMIT ?", (int(limit),)
    )
    for row in rows:
        row["validation_summary"] = json_loads(row.get("validation_summary"), {})
        row["column_mapping"] = json_loads(row.get("column_mapping"), {})
    return rows


def insert_sales_rows(db: Database, rows: list[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    return db.execute_many(
        """
        INSERT INTO sales_records (product_id, sale_date, quantity, unit_price, revenue,
                                   store, order_id, import_batch_id, is_demo, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def existing_signatures(db: Database) -> set[str]:
    """Existing (product_id|date|quantity|price) signatures for duplicate detection."""
    rows = db.query(
        """
        SELECT product_id, sale_date, quantity, COALESCE(unit_price, -1) AS unit_price
        FROM sales_records
        """
    )
    return {
        f"{row['product_id']}|{row['sale_date']}|{row['quantity']}|{row['unit_price']}"
        for row in rows
    }


def clear_sales(db: Database, *, data_source: str | None = None) -> int:
    if data_source == "demo":
        return db.execute("DELETE FROM sales_records WHERE is_demo = 1")
    if data_source == "actual":
        return db.execute("DELETE FROM sales_records WHERE is_demo = 0")
    return db.execute("DELETE FROM sales_records")
