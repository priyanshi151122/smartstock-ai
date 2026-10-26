"""Inventory state and stock movement ledger."""

from __future__ import annotations

from typing import Any

from app.db import Database
from app.utils import sanitize_text, utcnow_iso

INVENTORY_SELECT = """
SELECT i.*, p.sku, p.name, p.category, p.unit_cost, p.selling_price, p.is_whole_units,
       p.is_active, s.name AS supplier_name
FROM inventory i
JOIN products p ON p.id = i.product_id
LEFT JOIN suppliers s ON s.id = p.supplier_id
"""


def list_inventory(
    db: Database,
    *,
    search: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[dict[str, Any]], int]:
    where, params = ["p.is_active = 1"], []
    if search:
        needle = f"%{search.strip().lower()}%"
        where.append("(LOWER(p.name) LIKE ? OR LOWER(p.sku) LIKE ? OR LOWER(COALESCE(p.category,'')) LIKE ?)")
        params += [needle, needle, needle]
    if category:
        where.append("p.category = ?")
        params.append(category)
    where_sql = " WHERE " + " AND ".join(where)
    total = int(
        db.scalar(f"SELECT COUNT(*) AS c FROM inventory i JOIN products p ON p.id = i.product_id{where_sql}", params, 0)
        or 0
    )
    columns = {
        "name": "p.name",
        "sku": "p.sku",
        "current_stock": "i.current_stock",
        "reorder_threshold": "i.reorder_threshold",
        "lead_time_days": "i.lead_time_days",
        "category": "p.category",
        "value": "COALESCE(p.unit_cost, 0) * i.current_stock",
    }
    order_column = columns.get(sort_by, "p.name")
    direction = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
    offset = max(0, (page - 1) * page_size)
    rows = db.query(
        f"{INVENTORY_SELECT}{where_sql} ORDER BY {order_column} {direction}, p.name ASC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    )
    return rows, total


def get_inventory(db: Database, product_id: int) -> dict[str, Any] | None:
    return db.query_one(f"{INVENTORY_SELECT} WHERE i.product_id = ?", (product_id,))


def get_inventory_map(db: Database) -> dict[int, dict[str, Any]]:
    rows = db.query(f"{INVENTORY_SELECT} WHERE p.is_active = 1")
    return {int(row["product_id"]): row for row in rows}


def update_inventory(db: Database, product_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "current_stock",
        "reorder_threshold",
        "lead_time_days",
        "min_order_qty",
        "pack_size",
        "safety_stock_days",
        "review_period_days",
        "target_cover_days",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if updates:
        assignments = ", ".join(f"{column} = ?" for column in updates)
        db.execute(
            f"UPDATE inventory SET {assignments}, updated_at = ? WHERE product_id = ?",
            list(updates.values()) + [utcnow_iso(), product_id],
        )
    return get_inventory(db, product_id)


def ensure_inventory_row(
    db: Database,
    product_id: int,
    *,
    stock: float = 0,
    reorder_threshold: float = 0,
    lead_time_days: int = 7,
    min_order_qty: int = 1,
    pack_size: int = 1,
    safety_stock_days: float = 3,
    review_period_days: int = 7,
    target_cover_days: float | None = None,
) -> None:
    existing = db.query_one("SELECT product_id FROM inventory WHERE product_id = ?", (product_id,))
    if existing:
        return
    db.execute(
        """
        INSERT INTO inventory (product_id, current_stock, reorder_threshold, lead_time_days,
                               min_order_qty, pack_size, safety_stock_days, review_period_days,
                               target_cover_days, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            float(stock),
            float(reorder_threshold),
            int(lead_time_days),
            int(min_order_qty),
            int(pack_size),
            float(safety_stock_days),
            int(review_period_days),
            target_cover_days,
            utcnow_iso(),
        ),
    )


def set_stock(
    db: Database,
    product_id: int,
    new_stock: float,
    *,
    movement_type: str = "adjustment",
    reason: str | None = None,
    actor: str = "system",
    reference: str | None = None,
) -> dict[str, Any]:
    """Apply an absolute stock level and append an auditable movement row."""
    current = get_inventory(db, product_id)
    previous = float(current["current_stock"]) if current else 0.0
    ensure_inventory_row(db, product_id, stock=previous)
    new_stock = max(0.0, float(new_stock))
    db.execute(
        "UPDATE inventory SET current_stock = ?, updated_at = ? WHERE product_id = ?",
        (new_stock, utcnow_iso(), product_id),
    )
    record_movement(
        db,
        product_id=product_id,
        movement_type=movement_type,
        quantity_delta=new_stock - previous,
        previous_stock=previous,
        new_stock=new_stock,
        reason=reason,
        actor=actor,
        reference=reference,
    )
    return get_inventory(db, product_id) or {}


def record_movement(
    db: Database,
    *,
    product_id: int,
    movement_type: str,
    quantity_delta: float,
    previous_stock: float,
    new_stock: float,
    reason: str | None = None,
    actor: str = "system",
    reference: str | None = None,
) -> int:
    return int(
        db.execute(
            """
            INSERT INTO stock_movements (product_id, movement_type, quantity_delta, previous_stock,
                                         new_stock, reason, reference, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                movement_type,
                float(quantity_delta),
                float(previous_stock),
                float(new_stock),
                sanitize_text(reason, 280),
                sanitize_text(reference, 80),
                sanitize_text(actor, 80) or "system",
                utcnow_iso(),
            ),
        )
    )


def adjustments_allowed(current: float, delta: float) -> tuple[bool, str | None]:
    if current + delta < 0:
        return False, (
            f"Adjustment of {delta:+.2f} would take stock below zero "
            f"(current stock {current:.2f}). Record a correction instead."
        )
    return True, None


def list_movements(
    db: Database, *, product_id: int | None = None, limit: int = 100, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    where, params = "", []
    if product_id:
        where = " WHERE m.product_id = ?"
        params.append(int(product_id))
    total = int(
        db.scalar(
            f"SELECT COUNT(*) AS c FROM stock_movements m{where}", params, 0
        )
        or 0
    )
    rows = db.query(
        f"""
        SELECT m.*, p.name AS product_name, p.sku
        FROM stock_movements m
        JOIN products p ON p.id = m.product_id
        {where}
        ORDER BY m.created_at DESC, m.id DESC
        LIMIT ? OFFSET ?
        """,
        params + [int(limit), int(offset)],
    )
    return rows, total
