"""Products, suppliers and application settings."""

from __future__ import annotations

from typing import Any, Iterable

from app.db import Database
from app.utils import json_dumps, json_loads, sanitize_text, utcnow_iso

PRODUCT_SELECT = """
SELECT p.*, s.name AS supplier_name,
       i.current_stock, i.reorder_threshold, i.lead_time_days, i.min_order_qty,
       i.pack_size, i.safety_stock_days, i.review_period_days, i.target_cover_days,
       i.updated_at AS inventory_updated_at
FROM products p
LEFT JOIN suppliers s ON s.id = p.supplier_id
LEFT JOIN inventory i ON i.product_id = p.id
"""

SORTABLE_COLUMNS = {
    "name": "p.name",
    "sku": "p.sku",
    "category": "p.category",
    "created_at": "p.created_at",
    "current_stock": "i.current_stock",
    "reorder_threshold": "i.reorder_threshold",
    "lead_time_days": "i.lead_time_days",
}


# --------------------------------------------------------------------- suppliers
def get_or_create_supplier(db: Database, name: str, lead_time_days: int = 7) -> int:
    cleaned = sanitize_text(name, 160) or "Unknown supplier"
    existing = db.query_one("SELECT id FROM suppliers WHERE name = ?", (cleaned,))
    if existing:
        return int(existing["id"])
    return int(
        db.execute(
            "INSERT INTO suppliers (name, lead_time_days, created_at) VALUES (?, ?, ?)",
            (cleaned, int(lead_time_days), utcnow_iso()),
        )
    )


def list_suppliers(db: Database) -> list[dict[str, Any]]:
    return db.query("SELECT * FROM suppliers ORDER BY name")


# ---------------------------------------------------------------------- products
def list_products(
    db: Database,
    *,
    search: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
    product_ids: Iterable[int] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    where, params = ["p.is_active = 1"], []
    if search:
        where.append("(LOWER(p.name) LIKE ? OR LOWER(p.sku) LIKE ? OR LOWER(COALESCE(p.category,'')) LIKE ?)")
        needle = f"%{search.strip().lower()}%"
        params += [needle, needle, needle]
    if category:
        where.append("p.category = ?")
        params.append(category)
    if product_ids:
        ids = [int(i) for i in product_ids]
        where.append(f"p.id IN ({','.join('?' for _ in ids)})")
        params += ids

    where_sql = " WHERE " + " AND ".join(where)
    total = int(db.scalar(f"SELECT COUNT(*) AS c FROM products p{where_sql}", params, 0) or 0)
    order_column = SORTABLE_COLUMNS.get(sort_by, "p.name")
    direction = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
    offset = max(0, (page - 1) * page_size)
    rows = db.query(
        f"{PRODUCT_SELECT}{where_sql} ORDER BY {order_column} {direction}, p.id ASC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    )
    return rows, total


def all_products(db: Database) -> list[dict[str, Any]]:
    return db.query(f"{PRODUCT_SELECT} ORDER BY p.name")


def get_product(db: Database, product_id: int) -> dict[str, Any] | None:
    return db.query_one(f"{PRODUCT_SELECT} WHERE p.id = ?", (product_id,))


def get_product_by_sku(db: Database, sku: str) -> dict[str, Any] | None:
    return db.query_one(f"{PRODUCT_SELECT} WHERE p.sku = ?", (sku,))


def create_product(
    db: Database,
    *,
    sku: str,
    name: str,
    category: str | None = None,
    supplier_id: int | None = None,
    unit_cost: float | None = None,
    selling_price: float | None = None,
    uom: str = "unit",
    is_whole_units: bool = True,
    is_demo: bool = False,
    stock: float = 0,
    reorder_threshold: float = 0,
    lead_time_days: int = 7,
    min_order_qty: int = 1,
    pack_size: int = 1,
    safety_stock_days: float = 3,
    review_period_days: int = 7,
    target_cover_days: float | None = None,
) -> int:
    now = utcnow_iso()
    product_id = int(
        db.execute(
            """
            INSERT INTO products (sku, name, category, supplier_id, unit_cost, selling_price,
                                  uom, is_whole_units, is_demo, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                sanitize_text(sku, 64),
                sanitize_text(name, 200),
                sanitize_text(category, 120),
                supplier_id,
                unit_cost,
                selling_price,
                sanitize_text(uom, 24) or "unit",
                1 if is_whole_units else 0,
                1 if is_demo else 0,
                now,
                now,
            ),
        )
    )
    db.execute(
        """
        INSERT INTO inventory (product_id, current_stock, reorder_threshold, lead_time_days,
                               min_order_qty, pack_size, safety_stock_days, review_period_days,
                               target_cover_days, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            max(0.0, float(stock or 0)),
            max(0.0, float(reorder_threshold or 0)),
            int(lead_time_days),
            int(min_order_qty),
            int(pack_size),
            float(safety_stock_days),
            int(review_period_days),
            target_cover_days,
            now,
        ),
    )
    return product_id


def update_product(db: Database, product_id: int, fields: dict[str, Any]) -> bool:
    allowed = {
        "sku",
        "name",
        "category",
        "supplier_id",
        "unit_cost",
        "selling_price",
        "uom",
        "is_whole_units",
        "is_active",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False
    for boolean_field in ("is_whole_units", "is_active"):
        if boolean_field in updates:
            updates[boolean_field] = 1 if updates[boolean_field] else 0
    assignments = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values()) + [utcnow_iso(), product_id]
    db.execute(f"UPDATE products SET {assignments}, updated_at = ? WHERE id = ?", params)
    return True


def delete_product(db: Database, product_id: int) -> bool:
    """Soft delete: keeps historical sales/finance integrity."""
    db.execute(
        "UPDATE products SET is_active = 0, updated_at = ? WHERE id = ?",
        (utcnow_iso(), product_id),
    )
    return True


def categories(db: Database) -> list[str]:
    rows = db.query(
        "SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category <> '' ORDER BY category"
    )
    return [row["category"] for row in rows]


def count_products(db: Database) -> int:
    return int(db.scalar("SELECT COUNT(*) AS c FROM products WHERE is_active = 1", None, 0) or 0)


# ---------------------------------------------------------------------- settings
DEFAULT_SETTINGS: dict[str, str] = {
    "store_name": "SmartShop Local Market",
    "currency": "INR",
    "currency_symbol": "\u20b9",
    "currency_locale": "en-IN",
    "default_horizon_days": "14",
    "service_level_z": "1.65",
    "default_theme": "dark",
}


def get_settings_map(db: Database) -> dict[str, str]:
    rows = db.query("SELECT key, value FROM app_settings")
    stored = {row["key"]: row["value"] for row in rows}
    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
    return merged


def set_settings(db: Database, values: dict[str, Any]) -> dict[str, str]:
    now = utcnow_iso()
    for key, value in values.items():
        if key not in DEFAULT_SETTINGS or value is None:
            continue
        db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, str(value), now),
        )
    return get_settings_map(db)


def get_setting(db: Database, key: str, default: Any = None) -> Any:
    row = db.query_one("SELECT value FROM app_settings WHERE key = ?", (key,))
    if row:
        return row["value"]
    return DEFAULT_SETTINGS.get(key, default)


# --------------------------------------------------------------------- utilities
def data_source_counts(db: Database) -> dict[str, int]:
    rows = db.query(
        "SELECT is_demo, COUNT(*) AS c FROM sales_records GROUP BY is_demo"
    )
    counts = {"demo": 0, "actual": 0}
    for row in rows:
        counts["demo" if row["is_demo"] else "actual"] = int(row["c"])
    return counts


def audit_payload(details: dict[str, Any] | None) -> str:
    return json_dumps(details or {})


def decode_settings(raw: str | None) -> dict[str, Any]:
    return json_loads(raw, {}) or {}
