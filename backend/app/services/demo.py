"""Deterministic synthetic demo dataset.

The generated data is always flagged ``is_demo = 1`` in the database and labelled
as synthetic everywhere it surfaces in the API/UI. It is intended to let a new
installation explore the analytics, never to masquerade as real shop records.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import zlib

import numpy as np
import pandas as pd

from app.db import Database
from app.repositories import audit, catalog, sales as sales_repo
from app.utils import utcnow_iso

DEMO_SEED = 20240517
DEMO_START = date(2024, 10, 1)
DEMO_DAYS = 365

# sku, name, category, base daily units, price, cost, supplier, lead time
DEMO_PRODUCTS: list[tuple[str, str, str, float, float, float, str, int]] = [
    ("DAIRY-001", "Amul Taaza Toned Milk 1L", "Dairy", 42, 68.0, 58.0, "Amul Distributors", 2),
    ("DAIRY-002", "Amul Butter 500g", "Dairy", 9, 285.0, 244.0, "Amul Distributors", 3),
    ("DAIRY-003", "Mother Dairy Curd 400g", "Dairy", 18, 42.0, 34.0, "Mother Dairy", 2),
    ("DAIRY-004", "Britannia Cheese Slices 200g", "Dairy", 7, 145.0, 122.0, "Britannia Depot", 4),
    ("SNKS-001", "Lay's Classic Salted 52g", "Snacks", 34, 20.0, 15.5, "PepsiCo Foods", 5),
    ("SNKS-002", "Kurkure Masala Munch 90g", "Snacks", 26, 20.0, 15.0, "PepsiCo Foods", 5),
    ("SNKS-003", "Haldiram Aloo Bhujia 400g", "Snacks", 11, 110.0, 92.0, "Haldiram Depot", 6),
    ("SNKS-004", "Parle-G Biscuits 800g", "Snacks", 19, 90.0, 74.0, "Parle Products", 5),
    ("BEVG-001", "Tata Tea Premium 500g", "Beverages", 14, 265.0, 226.0, "Tata Consumer", 7),
    ("BEVG-002", "Nescafe Classic 100g", "Beverages", 6, 320.0, 274.0, "Nestle India", 7),
    ("BEVG-003", "Coca-Cola 1.25L", "Beverages", 29, 65.0, 52.0, "Coca-Cola Bottling", 4),
    ("BEVG-004", "Real Mixed Fruit Juice 1L", "Beverages", 12, 125.0, 104.0, "Dabur India", 6),
    ("STPL-001", "Aashirvaad Atta 5kg", "Staples", 8, 275.0, 238.0, "ITC Distribution", 8),
    ("STPL-002", "Tata Sampann Toor Dal 1kg", "Staples", 13, 165.0, 141.0, "Tata Consumer", 8),
    ("STPL-003", "Fortune Sunflower Oil 1L", "Staples", 21, 145.0, 126.0, "Adani Wilmar", 7),
    ("STPL-004", "India Gate Basmati Rice 5kg", "Staples", 5, 620.0, 548.0, "KRBL Depot", 10),
    ("STPL-005", "Tata Salt 1kg", "Staples", 24, 28.0, 22.0, "Tata Consumer", 6),
    ("HH-001", "Surf Excel Easy Wash 1kg", "Household", 15, 120.0, 101.0, "HUL Distributors", 6),
    ("HH-002", "Colgate Strong Teeth 200g", "Household", 17, 105.0, 86.0, "Colgate Palmolive", 6),
    ("HH-003", "Harpic Toilet Cleaner 1L", "Household", 8, 195.0, 165.0, "Reckitt Benckiser", 9),
    ("HH-004", "Vim Dishwash Bar 300g", "Household", 22, 32.0, 25.0, "HUL Distributors", 6),
    ("PERS-001", "Dove Soap 100g (pack of 3)", "Personal Care", 10, 210.0, 176.0, "HUL Distributors", 7),
    ("PERS-002", "Nivea Body Lotion 400ml", "Personal Care", 4, 375.0, 318.0, "Nivea India", 9),
    ("PERS-003", "Colgate Toothpaste 500g", "Personal Care", 9, 235.0, 199.0, "Colgate Palmolive", 6),
]

CATEGORY_SEASONALITY = {
    "Dairy": {"amplitude": 0.18, "phase": 0.0},
    "Snacks": {"amplitude": 0.30, "phase": 1.2},
    "Beverages": {"amplitude": 0.24, "phase": 1.6},
    "Staples": {"amplitude": 0.12, "phase": 0.4},
    "Household": {"amplitude": 0.10, "phase": 2.0},
    "Personal Care": {"amplitude": 0.15, "phase": 2.4},
}


def generate_demo_frame(
    seed: int = DEMO_SEED, days: int = DEMO_DAYS, start: date | None = None
) -> pd.DataFrame:
    """Generate deterministic daily line-item sales for 24 products.

    The window ends yesterday so the synthetic dataset always sits next to
    "today" for risk/cover calculations. The random stream itself is seeded, so
    rerunning with the same anchor date reproduces exactly the same numbers.
    """
    start = start or (date.today() - timedelta(days=days - 1))
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    order_counter = 0

    for sku_index, (sku, name, category, base, price, cost, supplier, lead) in enumerate(DEMO_PRODUCTS):
        seasonal = CATEGORY_SEASONALITY[category]
        # Product-level personality: weekday lift, weekend lift, volatility.
        weekend_lift = float(rng.uniform(1.05, 1.45))
        volatility = float(rng.uniform(0.12, 0.34))
        trend = float(rng.uniform(-0.18, 0.22))
        promo_days = set(rng.choice(np.arange(days), size=max(4, days // 45), replace=False).tolist())

        for day_offset in range(days):
            current = start + timedelta(days=day_offset)
            weekday = current.weekday()
            if rng.random() < 0.12:  # shop was closed / no record that day
                continue

            weekday_factor = [0.94, 0.97, 1.0, 1.02, 1.18, 1.32, 1.24][weekday]
            if weekday >= 5:
                weekday_factor *= weekend_lift
            seasonal_factor = 1 + seasonal["amplitude"] * np.sin(
                2 * np.pi * (day_offset / 365.0) + seasonal["phase"]
            )
            trend_factor = 1 + trend * (day_offset / days)
            promo_factor = 1.65 if day_offset in promo_days else 1.0
            noise = rng.normal(1.0, volatility)

            quantity = base * weekday_factor * seasonal_factor * trend_factor * promo_factor * noise
            quantity = max(0.0, round(quantity))
            if quantity == 0 and rng.random() < 0.5:
                continue  # genuine zero-sale days are simply not recorded as line items
            price_jitter = 1 + rng.uniform(-0.04, 0.06)
            unit_price = round(price * price_jitter, 2)
            if day_offset in promo_days:
                unit_price = round(unit_price * 0.92, 2)

            order_counter += 1
            rows.append(
                {
                    "sku": sku,
                    "product_name": name,
                    "category": category,
                    "date": current.isoformat(),
                    "quantity": float(quantity),
                    "unit_price": unit_price,
                    "unit_cost": cost,
                    "store": "SmartShop Main" if sku_index % 3 else "SmartShop Express",
                    "supplier": supplier,
                    "order_id": f"INV-{current.strftime('%Y%m%d')}-{(order_counter % 420) + 1:04d}",
                }
            )

    frame = pd.DataFrame(rows).sort_values(["date", "sku"]).reset_index(drop=True)
    return frame


def demo_inventory_targets(frame: pd.DataFrame, seed: int = DEMO_SEED) -> dict[str, dict[str, float]]:
    """Derive plausible stock levels so the demo shows a spread of risk states."""
    rng = np.random.default_rng(seed + 7)
    # Trailing 28-day average per SKU drives the simulated stock cover.
    trailing = frame.groupby("sku")["quantity"].apply(lambda values: float(values.tail(28).mean()))
    targets: dict[str, dict[str, float]] = {}
    scenarios = ["healthy", "low", "stockout", "overstock", "healthy", "medium"]
    for sku, daily in trailing.items():
        scenario = scenarios[zlib.crc32(sku.encode()) % len(scenarios)]
        cover_days = {
            "healthy": 16,
            "medium": 9,
            "low": 5,
            "stockout": 0,
            "overstock": 75,
        }[scenario]
        stock = 0.0 if scenario == "stockout" else max(0.0, round(daily * cover_days * rng.uniform(0.85, 1.15)))
        targets[sku] = {
            "current_stock": stock,
            "reorder_threshold": round(daily * 7, 2),
            "safety_stock_days": 3,
            "review_period_days": 7,
        }
    return targets


def build_validation_test_frame(seed: int = DEMO_SEED + 99) -> pd.DataFrame:
    """Small file full of deliberate data-quality problems (for testing validation)."""
    base = [
        {"sku": "DAIRY-001", "product_name": "Amul Taaza Toned Milk 1L", "category": "Dairy",
         "date": "2025-03-01", "quantity": 12, "unit_price": 68, "store": "Main"},
        {"sku": "DAIRY-001", "product_name": "Amul Taaza Toned Milk 1L", "category": "Dairy",
         "date": "2025-03-01", "quantity": 12, "unit_price": 68, "store": "Main"},  # duplicate
        {"sku": "SNKS-001", "product_name": "Lay's Classic Salted 52g", "category": "Snacks",
         "date": "2025-03-02", "quantity": -3, "unit_price": 20, "store": "Main"},  # negative
        {"sku": "", "product_name": "", "category": "Snacks",
         "date": "2025-03-02", "quantity": 5, "unit_price": 20, "store": "Main"},  # no identifier
        {"sku": "BEVG-001", "product_name": "Tata Tea Premium 500g", "category": "Beverages",
         "date": "not-a-date", "quantity": 4, "unit_price": 265, "store": "Main"},  # bad date
        {"sku": "BEVG-003", "product_name": "Coca-Cola 1.25L", "category": "Beverages",
         "date": "2025-03-03", "quantity": "", "unit_price": 65, "store": "Main"},  # missing qty
        {"sku": "STPL-005", "product_name": "Tata Salt 1kg", "category": "Staples",
         "date": "03/04/2025", "quantity": "18", "unit_price": "\u20b928.00", "store": "Main"},  # messy but fixable
        {"sku": "stpl-003", "product_name": "Fortune Sunflower Oil 1L", "category": "staples",
         "date": "2025-03-04", "quantity": 9, "unit_price": 145, "store": "Express"},  # casing
        {"sku": "HH-001", "product_name": "Surf Excel Easy Wash 1kg", "category": "Household",
         "date": "2025-03-05", "quantity": 6, "unit_price": "", "store": "Main"},  # missing price
        {"sku": "HH-002", "product_name": "Colgate Strong Teeth 200g", "category": "Household",
         "date": "2025-03-05", "quantity": "seven", "unit_price": 105, "store": "Main"},  # bad qty
    ]
    return pd.DataFrame(base)


def seed_demo_data(db: Database, *, reset: bool = True, seed: int = DEMO_SEED) -> dict[str, Any]:
    """Insert the synthetic dataset (idempotent when reset=True)."""
    if reset:
        sales_repo.clear_sales(db, data_source="demo")

    existing_rows = int(db.scalar("SELECT COUNT(*) AS c FROM sales_records WHERE is_demo = 1", None, 0) or 0)
    if existing_rows:
        return {
            "inserted_rows": 0,
            "products": int(db.scalar("SELECT COUNT(*) AS c FROM products WHERE is_demo = 1", None, 0) or 0),
            "message": "Demo data already present; nothing was inserted.",
            "already_loaded": True,
        }

    frame = generate_demo_frame(seed=seed)
    targets = demo_inventory_targets(frame, seed=seed)
    now = utcnow_iso()

    supplier_ids: dict[str, int] = {}
    product_ids: dict[str, int] = {}
    for sku, name, category, _base, price, cost, supplier, lead in DEMO_PRODUCTS:
        if supplier not in supplier_ids:
            supplier_ids[supplier] = catalog.get_or_create_supplier(db, supplier, lead)
        stock_info = targets.get(sku, {})
        product_ids[sku] = catalog.create_product(
            db,
            sku=sku,
            name=name,
            category=category,
            supplier_id=supplier_ids[supplier],
            unit_cost=cost,
            selling_price=price,
            is_demo=True,
            stock=stock_info.get("current_stock", 0),
            reorder_threshold=stock_info.get("reorder_threshold", 0),
            lead_time_days=lead,
            min_order_qty=6,
            pack_size=6 if category in {"Dairy", "Beverages"} else 1,
            safety_stock_days=float(stock_info.get("safety_stock_days", 3)),
            review_period_days=7,
        )

    batch_id = sales_repo.create_import_batch(
        db,
        filename="demo_sales_12_months.csv",
        file_type="csv",
        file_size_bytes=int(len(frame) * 90),
        status="imported",
        data_source="demo",
        column_mapping={"sku": "sku", "date": "date", "quantity": "quantity", "unit_price": "unit_price"},
        message="Synthetic demo dataset generated with a fixed random seed.",
    )
    rows = [
        (
            product_ids[record["sku"]],
            record["date"],
            float(record["quantity"]),
            float(record["unit_price"]),
            round(float(record["quantity"]) * float(record["unit_price"]), 2),
            record["store"],
            record["order_id"],
            batch_id,
            1,
            now,
        )
        for _, record in frame.iterrows()
        if record["sku"] in product_ids
    ]
    inserted = sales_repo.insert_sales_rows(db, rows)
    sales_repo.update_import_batch(
        db,
        batch_id,
        {
            "total_rows": len(frame),
            "valid_rows": len(frame),
            "invalid_rows": 0,
            "imported_rows": inserted,
            "completed_at": now,
            "validation_summary": {"synthetic": True, "seed": seed, "products": len(DEMO_PRODUCTS)},
        },
    )
    audit.log(
        db,
        action="demo.loaded",
        entity_type="import_batch",
        entity_id=batch_id,
        actor="demo-seeder",
        details={"rows": inserted, "products": len(DEMO_PRODUCTS), "seed": seed},
    )
    return {
        "inserted_rows": inserted,
        "products": len(DEMO_PRODUCTS),
        "batch_id": batch_id,
        "message": (
            f"Loaded {inserted:,} synthetic sales rows for {len(DEMO_PRODUCTS)} demo products. "
            "These records are labelled as demo data everywhere in the app."
        ),
        "already_loaded": False,
        "seed": seed,
        "date_range": {"start": frame["date"].min(), "end": frame["date"].max()},
    }


def clear_demo_data(db: Database) -> dict[str, Any]:
    removed = sales_repo.clear_sales(db, data_source="demo")
    product_ids = [row["id"] for row in db.query("SELECT id FROM products WHERE is_demo = 1")]
    if product_ids:
        placeholders = ",".join("?" for _ in product_ids)
        db.execute(f"DELETE FROM inventory WHERE product_id IN ({placeholders})", product_ids)
        db.execute(f"DELETE FROM products WHERE id IN ({placeholders})", product_ids)
    audit.log(
        db,
        action="demo.cleared",
        entity_type="sales_records",
        actor="demo-seeder",
        details={"removed_rows": removed, "removed_products": len(product_ids)},
    )
    return {
        "removed_rows": removed,
        "removed_products": len(product_ids),
        "message": "Demo dataset removed. Real imported records were left untouched.",
    }
