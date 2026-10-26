"""Inventory mathematics: reorder points, safety stock, risk and recommendations.

The core functions in this module are pure and unit tested (see
``backend/tests/test_inventory_logic.py``). Every recommendation is produced with
a human readable explanation that quotes the exact inputs used.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from app.db import Database
from app.repositories import catalog, inventory as inventory_repo, sales as sales_repo
from app.utils import ceil_units, round2

RISK_ORDER = {"stockout": 0, "high": 1, "medium": 2, "low": 3, "overstock": 4, "unknown": 5}


# ------------------------------------------------------------------ pure maths
def average_daily_demand(forecast_demand: float | None, horizon_days: int) -> float:
    """Average daily demand = forecasted demand over horizon / days in horizon."""
    if not forecast_demand or horizon_days <= 0:
        return 0.0
    return float(forecast_demand) / float(horizon_days)


def safety_stock(
    avg_daily_demand_value: float,
    daily_demand_std: float | None,
    lead_time_days: int,
    *,
    z: float = 1.65,
    safety_days: float = 0.0,
) -> tuple[float, str]:
    """Safety stock = max(z * sigma_daily * sqrt(lead time), avg daily demand * buffer days)."""
    statistical = (
        z * float(daily_demand_std) * math.sqrt(max(0, lead_time_days))
        if daily_demand_std and daily_demand_std > 0 and lead_time_days > 0
        else 0.0
    )
    buffer = float(avg_daily_demand_value) * float(max(0.0, safety_days))
    value = max(statistical, buffer)
    if statistical >= buffer and statistical > 0:
        reason = (
            f"statistical buffer z={z:g} x sigma={daily_demand_std:.2f} x sqrt(lead time {lead_time_days}d) "
            f"= {statistical:.2f}"
        )
    elif buffer > 0:
        reason = (
            f"configured buffer {safety_days:g} days x avg daily demand {avg_daily_demand_value:.2f} "
            f"= {buffer:.2f}"
        )
    else:
        reason = "no variability or buffer setting available"
    return max(0.0, value), reason


def reorder_point(avg_daily_demand_value: float, lead_time_days: int, safety_stock_value: float) -> float:
    """Reorder point = average daily demand x supplier lead time + safety stock."""
    return max(0.0, float(avg_daily_demand_value) * float(max(0, lead_time_days)) + float(safety_stock_value))


def target_stock_level(
    avg_daily_demand_value: float,
    lead_time_days: int,
    review_period_days: int,
    safety_stock_value: float,
    target_cover_days: float | None = None,
) -> float:
    """Target stock covers lead time + review period (or an explicit cover target)."""
    cover_days = (
        float(target_cover_days)
        if target_cover_days is not None and target_cover_days > 0
        else float(max(0, lead_time_days) + max(0, review_period_days))
    )
    return max(0.0, float(avg_daily_demand_value) * cover_days + float(safety_stock_value))


def suggested_quantity(
    target_stock: float,
    current_stock: float,
    *,
    min_order_qty: int = 1,
    pack_size: int = 1,
    is_whole_units: bool = True,
) -> float:
    """Suggested reorder quantity = max(0, target - current), respecting MOQ/pack size."""
    gap = float(target_stock) - float(current_stock)
    if gap <= 1e-9:
        return 0.0
    pack = max(1, int(pack_size or 1))
    packs = math.ceil(round(gap / pack, 6))
    quantity = packs * pack
    minimum = max(1, int(min_order_qty or 1))
    quantity = max(quantity, minimum)
    # Keep the MOQ aligned with the pack size when both are configured.
    if quantity % pack != 0:
        quantity = math.ceil(quantity / pack) * pack
    if is_whole_units:
        return float(ceil_units(quantity))
    return float(round(quantity, 2))


def days_of_cover(current_stock: float, avg_daily_demand_value: float) -> float | None:
    if avg_daily_demand_value <= 0:
        return None
    return float(current_stock) / float(avg_daily_demand_value)


def classify_risk(
    *,
    current_stock: float,
    avg_daily_demand_value: float,
    reorder_point_value: float,
    lead_time_days: int,
    review_period_days: int,
    target_stock: float,
    overstock_cover_days: float = 60.0,
) -> tuple[str, str]:
    """Return (risk_level, human readable reason)."""
    cover = days_of_cover(current_stock, avg_daily_demand_value)

    if avg_daily_demand_value <= 0:
        if current_stock > 0:
            return "overstock", (
                f"No demand in the reference window but {current_stock:g} units are on hand "
                "— working capital is tied up in idle stock."
            )
        return "low", "No demand and no stock on hand; nothing to action."

    if current_stock <= 0:
        return "stockout", (
            f"Stock is {current_stock:g} while average daily demand is {avg_daily_demand_value:.2f} "
            "units — the product is out of stock and losing sales."
        )
    if cover is not None and cover < float(lead_time_days):
        return "high", (
            f"Only {cover:.1f} days of cover at {avg_daily_demand_value:.2f} units/day, "
            f"but the supplier needs {lead_time_days} days — stock may run out before delivery."
        )
    if current_stock <= reorder_point_value:
        return "high", (
            f"Stock {current_stock:g} is at or below the reorder point {reorder_point_value:.1f}."
        )
    if cover is not None and cover < float(lead_time_days + review_period_days):
        return "medium", (
            f"{cover:.1f} days of cover is below lead time + review period "
            f"({lead_time_days}+{review_period_days} days); schedule a reorder this cycle."
        )
    if cover is not None and cover > overstock_cover_days:
        return "overstock", (
            f"{cover:.1f} days of cover exceeds the {overstock_cover_days:g}-day target "
            f"({current_stock:g} units on hand vs target {target_stock:.1f})."
        )
    if (
        target_stock > 0
        and current_stock > target_stock * 3
        and (cover or 0) > 30
    ):
        return "overstock", (
            f"Stock {current_stock:g} is more than three times the target level "
            f"{target_stock:.1f} with {cover:.1f} days of cover — likely excess inventory."
        )
    return "low", (
        f"{cover:.1f} days of cover with {current_stock:g} units on hand is within the healthy range."
    )


def build_recommendation(
    *,
    product: dict[str, Any],
    inventory: dict[str, Any],
    forecast_demand: float | None,
    horizon_days: int,
    daily_std: float | None,
    demand_source: str,
    service_level_z: float = 1.65,
    reference_daily: float | None = None,
) -> dict[str, Any]:
    """Combine the pure formulas into one explainable recommendation record."""
    current_stock = float(inventory.get("current_stock") or 0)
    lead_time = int(inventory.get("lead_time_days") or 0)
    review_period = int(inventory.get("review_period_days") or 0)
    min_order_qty = int(inventory.get("min_order_qty") or 1)
    pack_size = int(inventory.get("pack_size") or 1)
    safety_days = float(inventory.get("safety_stock_days") or 0)
    target_cover = inventory.get("target_cover_days")

    if forecast_demand is None and reference_daily is not None:
        forecast_demand = float(reference_daily) * float(horizon_days)

    avg_daily = average_daily_demand(forecast_demand, horizon_days)
    safety_value, safety_reason = safety_stock(
        avg_daily, daily_std, lead_time, z=service_level_z, safety_days=safety_days
    )
    rop = reorder_point(avg_daily, lead_time, safety_value)
    target = target_stock_level(avg_daily, lead_time, review_period, safety_value, target_cover)
    quantity = suggested_quantity(
        target,
        current_stock,
        min_order_qty=min_order_qty,
        pack_size=pack_size,
        is_whole_units=bool(inventory.get("is_whole_units", 1)),
    )
    risk_level, reason = classify_risk(
        current_stock=current_stock,
        avg_daily_demand_value=avg_daily,
        reorder_point_value=rop,
        lead_time_days=lead_time,
        review_period_days=review_period,
        target_stock=target,
    )
    cover = days_of_cover(current_stock, avg_daily)

    unit_cost = product.get("unit_cost")
    estimated_cost = round(float(unit_cost) * quantity, 2) if unit_cost is not None and quantity else None

    source_label = (
        f"forecast run (next {horizon_days} days)" if demand_source == "forecast"
        else f"trailing demand (last {horizon_days} days)"
    )
    cover_target_label = (
        f"target cover {float(target_cover):g} days"
        if target_cover
        else f"lead time {lead_time}d + review period {review_period}d"
    )
    explanation = (
        f"Demand source: {source_label} = {float(forecast_demand or 0):.1f} units, "
        f"so average daily demand = {float(forecast_demand or 0):.1f} / {horizon_days} = {avg_daily:.2f} units/day. "
        f"Safety stock = {safety_value:.1f} ({safety_reason}). "
        f"Reorder point = {avg_daily:.2f} x {lead_time}d lead time + {safety_value:.1f} = {rop:.1f}. "
        f"Target stock = {avg_daily:.2f} x ({cover_target_label}) + {safety_value:.1f} = {target:.1f}. "
        f"Current stock {current_stock:g} → suggested order = max(0, {target:.1f} - {current_stock:g}) "
        f"rounded to pack size {pack_size} with minimum order {min_order_qty} = {quantity:g} units. "
        f"Risk: {risk_level.upper()} — {reason}"
    )

    return {
        "product_id": int(product["id"]),
        "risk_level": risk_level,
        "current_stock": current_stock,
        "forecast_horizon_days": horizon_days,
        "forecast_demand": round(float(forecast_demand or 0), 2),
        "avg_daily_demand": round(avg_daily, 4),
        "demand_std": round2(daily_std),
        "safety_stock": round(safety_value, 2),
        "reorder_point": round(rop, 2),
        "target_stock": round(target, 2),
        "suggested_quantity": quantity,
        "estimated_cost": estimated_cost,
        "lead_time_days": lead_time,
        "min_order_qty": min_order_qty,
        "pack_size": pack_size,
        "coverage_days": round2(cover),
        "explanation": explanation,
        "demand_source": demand_source,
        "risk_reason": reason,
    }


# ---------------------------------------------------------------- DB-level views
def _scope_records(
    inventory_map: dict[int, dict[str, Any]],
    *,
    category: str | None = None,
    product_id: int | None = None,
) -> list[dict[str, Any]]:
    records = [record for record in inventory_map.values() if int(record.get("is_active") or 1) == 1]
    if category:
        records = [record for record in records if record.get("category") == category]
    if product_id:
        records = [record for record in records if int(record["product_id"]) == int(product_id)]
    return records


def assess_risks(
    db: Database,
    *,
    inventory_map: dict[int, dict[str, Any]] | None = None,
    forecast_cov: dict[int, dict[str, Any]] | None = None,
    category: str | None = None,
    product_id: int | None = None,
    data_source: str | None = None,
    settings: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Risk assessment for every product in scope (forecast-based when available)."""
    inventory_map = inventory_map or inventory_repo.get_inventory_map(db)
    settings = settings or catalog.get_settings_map(db)
    demand_window = 28
    trailing = sales_repo.recent_demand_by_product(
        db, days=demand_window, data_source=data_source
    )
    records = _scope_records(inventory_map, category=category, product_id=product_id)
    if not records:
        return {
            "items": [],
            "counts": {key: 0 for key in RISK_ORDER},
            "summary": {"products": 0, "inventory_value": None, "avg_cover_days": None},
            "forecast_total_demand": None,
            "demand_window_days": demand_window,
        }

    items: list[dict[str, Any]] = []
    total_forecast = 0.0
    forecast_used = False
    for record in records:
        pid = int(record["product_id"])
        cov = (forecast_cov or {}).get(pid)
        if cov and cov.get("total_demand", 0) > 0:
            horizon = int(cov.get("horizon_days") or settings.get("default_horizon_days", 14))
            daily = cov["total_demand"] / horizon
            source = "forecast"
            total_forecast += float(cov["total_demand"])
            forecast_used = True
        else:
            trailing_rec = trailing.get(pid)
            daily = (trailing_rec or {}).get("daily_avg", 0.0)
            horizon = demand_window
            source = "trailing-demand"
            total_forecast += daily * int(settings.get("default_horizon_days", 14))

        current_stock = float(record.get("current_stock") or 0)
        lead = int(record.get("lead_time_days") or 0)
        review = int(record.get("review_period_days") or 0)
        safety_days = float(record.get("safety_stock_days") or 0)
        safety_value, _ = safety_stock(
            daily, None, lead, z=float(settings.get("service_level_z", 1.65)), safety_days=safety_days
        )
        rop = reorder_point(daily, lead, safety_value)
        target = target_stock_level(daily, lead, review, safety_value, record.get("target_cover_days"))
        risk_level, reason = classify_risk(
            current_stock=current_stock,
            avg_daily_demand_value=daily,
            reorder_point_value=rop,
            lead_time_days=lead,
            review_period_days=review,
            target_stock=target,
        )
        items.append(
            {
                "product_id": pid,
                "sku": record.get("sku"),
                "name": record.get("name"),
                "category": record.get("category"),
                "supplier_name": record.get("supplier_name"),
                "current_stock": round2(current_stock),
                "avg_daily_demand": round(daily, 3),
                "forecast_demand": round2(daily * horizon),
                "horizon_days": horizon,
                "demand_source": source,
                "reorder_point": round2(rop),
                "target_stock": round2(target),
                "safety_stock": round2(safety_value),
                "coverage_days": round2(days_of_cover(current_stock, daily)),
                "risk_level": risk_level,
                "risk_reason": reason,
                "stock_value": round2(
                    current_stock * float(record["unit_cost"]) if record.get("unit_cost") else None
                ),
            }
        )

    items.sort(key=lambda item: (RISK_ORDER.get(item["risk_level"], 9), -(item["current_stock"] or 0)))
    counts = {key: 0 for key in RISK_ORDER}
    for item in items:
        counts[item["risk_level"]] = counts.get(item["risk_level"], 0) + 1
    covers = [item["coverage_days"] for item in items if item["coverage_days"] is not None]
    inventory_value = sum(item["stock_value"] for item in items if item["stock_value"] is not None)
    has_cost = any(item["stock_value"] is not None for item in items)

    return {
        "items": items,
        "counts": counts,
        "summary": {
            "products": len(items),
            "inventory_value": round2(inventory_value) if has_cost else None,
            "avg_cover_days": round(sum(covers) / len(covers), 1) if covers else None,
            "stockout_units_at_risk": round2(
                sum(item["avg_daily_demand"] * item["horizon_days"] for item in items if item["risk_level"] == "stockout")
            ),
        },
        "forecast_total_demand": round2(total_forecast) if forecast_used else None,
        "demand_window_days": demand_window,
        "demand_source": "forecast" if forecast_used else "trailing-demand",
    }


def stock_vs_forecast_payload(risk: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    """Compact rows for the 'current stock vs forecast demand' chart."""
    items = risk.get("items", [])[:limit]
    return [
        {
            "product_id": item["product_id"],
            "name": item["name"],
            "sku": item["sku"],
            "current_stock": item["current_stock"],
            "forecast_demand": item["forecast_demand"],
            "horizon_days": item["horizon_days"],
            "reorder_point": item["reorder_point"],
            "risk_level": item["risk_level"],
            "demand_source": item["demand_source"],
        }
        for item in items
    ]


def generate_recommendations(
    db: Database,
    *,
    run_id: int | None = None,
    horizon_days: int | None = None,
    category: str | None = None,
    service_level_z: float | None = None,
    data_source: str | None = None,
    actor: str = "planner",
) -> dict[str, Any]:
    """Build and persist the recommendation table for the latest forecast."""
    from app.repositories import forecasts as forecast_repo

    settings = catalog.get_settings_map(db)
    run = None
    if run_id:
        run = forecast_repo.get_run(db, run_id)
        if not run:
            raise ValueError(f"Forecast run {run_id} was not found.")
    else:
        run = forecast_repo.latest_run(db, data_source=data_source or "actual") or forecast_repo.latest_run(db)

    horizon = int(horizon_days or (run["horizon_days"] if run else settings.get("default_horizon_days", 14)))
    forecast_cov = forecast_repo.forecast_totals(db, run["id"]) if run else {}
    demand_stats = sales_repo.demand_stats(db, data_source=data_source, end_date=None)
    inventory_map = inventory_repo.get_inventory_map(db)
    z = float(service_level_z if service_level_z is not None else settings.get("service_level_z", 1.65))
    window = 28
    trailing = sales_repo.recent_demand_by_product(db, days=window, data_source=data_source)

    records = _scope_records(inventory_map, category=category)
    payloads: list[dict[str, Any]] = []
    for record in records:
        pid = int(record["product_id"])
        cov = forecast_cov.get(pid)
        if cov and cov.get("total_demand", 0) > 0:
            forecast_demand = float(cov["total_demand"])
            horizon_for_product = int(cov.get("horizon_days") or horizon)
            source = "forecast"
        else:
            trailing_rec = trailing.get(pid, {})
            forecast_demand = float(trailing_rec.get("daily_avg", 0.0)) * horizon
            horizon_for_product = horizon
            source = "trailing-demand"
        stat = demand_stats.get(pid, {})
        payloads.append(
            build_recommendation(
                product=record,
                inventory={**record, "is_whole_units": record.get("is_whole_units", 1)},
                forecast_demand=forecast_demand,
                horizon_days=horizon_for_product,
                daily_std=stat.get("std") if stat else None,
                demand_source=source,
                service_level_z=z,
            )
        )

    forecast_repo.replace_open_recommendations(db, run["id"] if run else None)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    rows = [
        (
            payload["product_id"],
            run["id"] if run else None,
            "pending",
            payload["risk_level"],
            payload["current_stock"],
            payload["forecast_horizon_days"],
            payload["forecast_demand"],
            payload["avg_daily_demand"],
            payload["demand_std"],
            payload["safety_stock"],
            payload["reorder_point"],
            payload["target_stock"],
            payload["suggested_quantity"],
            payload["estimated_cost"],
            payload["lead_time_days"],
            payload["min_order_qty"],
            payload["pack_size"],
            payload["coverage_days"],
            payload["explanation"],
            payload["demand_source"],
            now,
        )
        for payload in payloads
    ]
    forecast_repo.insert_recommendations(db, rows)
    return {
        "run_id": run["id"] if run else None,
        "horizon_days": horizon,
        "created": len(rows),
        "service_level_z": z,
        "forecast_used": bool(forecast_cov),
        "demand_source": "forecast" if forecast_cov else "trailing-demand",
    }


def inventory_overview(
    db: Database,
    *,
    search: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
    data_source: str | None = None,
    settings: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Paginated inventory rows enriched with demand, cover and risk."""
    settings = settings or catalog.get_settings_map(db)
    from app.repositories import forecasts as forecast_repo

    rows, total = inventory_repo.list_inventory(
        db, search=search, category=category, page=page, page_size=page_size,
        sort_by=sort_by, sort_dir=sort_dir,
    )
    run = forecast_repo.latest_run(db, data_source=data_source)
    forecast_cov = forecast_repo.forecast_totals(db, run["id"]) if run else {}
    trailing = sales_repo.recent_demand_by_product(db, days=28, data_source=data_source)
    full_inventory = inventory_repo.get_inventory_map(db)
    risk = assess_risks(
        db,
        inventory_map=full_inventory,
        forecast_cov=forecast_cov,
        data_source=data_source,
        settings=settings,
    )
    risk_by_product = {item["product_id"]: item for item in risk["items"]}

    items = []
    for row in rows:
        pid = int(row["product_id"])
        risk_row = risk_by_product.get(pid, {})
        daily = risk_row.get("avg_daily_demand")
        if daily is None:
            daily = (trailing.get(pid) or {}).get("daily_avg", 0.0)
        stock = float(row.get("current_stock") or 0)
        items.append(
            {
                "product_id": pid,
                "sku": row["sku"],
                "name": row["name"],
                "category": row.get("category"),
                "supplier_name": row.get("supplier_name"),
                "current_stock": round2(stock),
                "reorder_threshold": round2(float(row.get("reorder_threshold") or 0)),
                "lead_time_days": int(row.get("lead_time_days") or 0),
                "min_order_qty": int(row.get("min_order_qty") or 1),
                "pack_size": int(row.get("pack_size") or 1),
                "safety_stock_days": round2(float(row.get("safety_stock_days") or 0)),
                "review_period_days": int(row.get("review_period_days") or 0),
                "target_cover_days": row.get("target_cover_days"),
                "unit_cost": round2(row.get("unit_cost")),
                "selling_price": round2(row.get("selling_price")),
                "stock_value": round2(stock * float(row["unit_cost"])) if row.get("unit_cost") else None,
                "recent_daily_demand": round(float(daily or 0), 3),
                "days_of_cover": risk_row.get("coverage_days")
                if risk_row.get("coverage_days") is not None
                else (round2(days_of_cover(stock, float(daily or 0)))),
                "risk_level": risk_row.get("risk_level", "unknown"),
                "risk_reason": risk_row.get("risk_reason"),
                "updated_at": row.get("updated_at"),
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, math.ceil(total / page_size)) if page_size else 1,
        "summary": {
            **risk["summary"],
            "counts": risk["counts"],
            "demand_source": risk["demand_source"],
            "forecast_run_id": run["id"] if run else None,
            "total_skus": total,
        },
    }
