"""Sales analytics: KPIs, time series, product performance and ABC analysis."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

from app.db import Database
from app.repositories import catalog, forecasts, inventory as inventory_repo, sales as sales_repo
from app.utils import human_period, round2, safe_divide, to_date, utcnow_iso

# ------------------------------------------------------------------ period math


def resolve_period(
    start_date: date | str | None,
    end_date: date | str | None,
    data_source: str | None = None,
    db: Database | None = None,
) -> tuple[date | None, date | None]:
    """Fill a missing bound from the actual data range so defaults are honest.

    Accepts ``date`` objects or ISO strings: report builders pass the raw filter
    dictionary, and every downstream calculation needs real dates.
    """
    resolved_start = to_date(start_date) if start_date else None
    resolved_end = to_date(end_date) if end_date else None
    if db is not None and (resolved_start is None or resolved_end is None):
        first, last = sales_repo.distinct_dates(db)
        if resolved_start is None:
            resolved_start = date.fromisoformat(first) if first else None
        if resolved_end is None:
            resolved_end = date.fromisoformat(last) if last else None
    return resolved_start, resolved_end


def previous_period(start: date | None, end: date | None) -> tuple[date | None, date | None]:
    """Equivalent length window immediately preceding the selected period."""
    if not start or not end:
        return None, None
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    return prev_start, prev_end


def filters_dict(
    start: date | None, end: date | None, category: str | None, product_id: int | None, data_source: str | None
) -> dict[str, Any]:
    return {
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "category": category,
        "product_id": product_id,
        "data_source": data_source,
    }


# ---------------------------------------------------------------------- KPIs
def _fmt_currency(value: float, symbol: str) -> str:
    if abs(value) >= 10_000_000:
        return f"{symbol}{value / 10_000_000:.2f} Cr"
    if abs(value) >= 100_000:
        return f"{symbol}{value / 100_000:.2f} L"
    return f"{symbol}{value:,.0f}"


def _fmt_number(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs(value) >= 10_000:
        return f"{value:,.0f}"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


def _change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / abs(previous) * 100, 1)


def compute_kpis(
    db: Database,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    product_id: int | None = None,
    data_source: str | None = None,
    settings: dict[str, str] | None = None,
) -> dict[str, Any]:
    settings = settings or catalog.get_settings_map(db)
    symbol = settings.get("currency_symbol", "\u20b9")
    start, end = resolve_period(start_date, end_date, data_source, db)
    base_filters = {
        "start_date": start,
        "end_date": end,
        "category": category,
        "product_id": product_id,
        "data_source": data_source,
    }
    current = sales_repo.totals(db, **base_filters)
    prev_start, prev_end = previous_period(start, end)
    previous = (
        sales_repo.totals(
            db,
            start_date=prev_start,
            end_date=prev_end,
            category=category,
            product_id=product_id,
            data_source=data_source,
        )
        if prev_start
        else {}
    )

    # Only claim a comparison when the previous window actually holds records.
    previous_rows = int(previous.get("rows") or 0)
    comparison_label = (
        f"vs previous period ({prev_start.isoformat()} – {prev_end.isoformat()})"
        if prev_start and previous_rows
        else "no prior-period records to compare"
    )

    revenue = float(current.get("revenue") or 0)
    units = float(current.get("units") or 0)
    products = int(current.get("products") or 0)
    orders = int(current.get("orders") or 0)
    has_order_data = orders > 1 and orders < int(current.get("rows") or 0) + 1 and orders > 0
    # An "order" column is only meaningful when it actually groups rows.
    rows_count = int(current.get("rows") or 0)
    has_order_data = bool(orders and rows_count and orders < rows_count)

    inventory_map = inventory_repo.get_inventory_map(db)
    scope_inventory = [
        record
        for pid, record in inventory_map.items()
        if (product_id is None or pid == product_id) and (not category or record.get("category") == category)
    ]
    inventory_value = None
    if scope_inventory and any(record.get("unit_cost") is not None for record in scope_inventory):
        inventory_value = sum(
            float(record.get("current_stock") or 0) * float(record.get("unit_cost") or 0)
            for record in scope_inventory
        )

    # Inventory risk from the latest forecast when one exists, else trailing demand.
    run = forecasts.latest_run(db, data_source=data_source)
    forecast_cov = forecasts.forecast_totals(db, run["id"]) if run else {}
    from app.services.inventory_logic import assess_risks

    risk = assess_risks(
        db,
        inventory_map=inventory_map,
        forecast_cov=forecast_cov,
        category=category,
        product_id=product_id,
        data_source=data_source,
        settings=settings,
    )

    avg_order_value = safe_divide(revenue, orders) if has_order_data else None
    avg_daily_units = safe_divide(units, max(1, int(current.get("active_days") or 0)))
    horizon = int(settings.get("default_horizon_days", 14))
    forecast_demand = risk.get("forecast_total_demand")
    if forecast_demand is None and avg_daily_units is not None:
        forecast_demand = None  # never invent a forecast from a stale average

    cards: list[dict[str, Any]] = [
        {
            "key": "total_revenue",
            "label": "Total Revenue",
            "value": round2(revenue),
            "unit": "currency",
            "formatted": _fmt_currency(revenue, symbol),
            "change_pct": _change(revenue, previous.get("revenue")) if previous_rows else None,
            "comparison_label": comparison_label,
            "available": rows_count > 0,
            "note": None if rows_count else "No sales records in the selected period.",
        },
        {
            "key": "total_units",
            "label": "Total Units Sold",
            "value": round2(units),
            "unit": "units",
            "formatted": _fmt_number(units),
            "change_pct": _change(units, previous.get("units")) if previous_rows else None,
            "comparison_label": comparison_label,
            "available": rows_count > 0,
        },
        {
            "key": "product_count",
            "label": "Products Sold",
            "value": products,
            "unit": "count",
            "formatted": f"{products:,}",
            "change_pct": None,
            "comparison_label": f"of {catalog.count_products(db)} active products",
            "available": True,
        },
        {
            "key": "avg_order_value",
            "label": "Average Order Value",
            "value": round2(avg_order_value),
            "unit": "currency",
            "formatted": _fmt_currency(avg_order_value, symbol) if avg_order_value is not None else "—",
            "available": avg_order_value is not None,
            "note": (
                None
                if avg_order_value is not None
                else "Requires an order/invoice column with more than one line per order."
            ),
        },
        {
            "key": "inventory_value",
            "label": "Inventory Value",
            "value": round2(inventory_value),
            "unit": "currency",
            "formatted": _fmt_currency(inventory_value, symbol) if inventory_value is not None else "—",
            "available": inventory_value is not None,
            "note": (
                None
                if inventory_value is not None
                else "Requires unit cost on the product master (or an imported cost column)."
            ),
        },
        {
            "key": "stockout_risk",
            "label": "Stockout Risk",
            "value": int(risk["counts"].get("stockout", 0) + risk["counts"].get("high", 0)),
            "unit": "count",
            "formatted": f"{int(risk['counts'].get('stockout', 0) + risk['counts'].get('high', 0)):,}",
            "available": True,
            "tone": "danger" if risk["counts"].get("stockout") else "warning",
            "comparison_label": f"{int(risk['counts'].get('stockout', 0))} stockout · {int(risk['counts'].get('high', 0))} high risk",
        },
        {
            "key": "overstock",
            "label": "Overstocked Products",
            "value": int(risk["counts"].get("overstock", 0)),
            "unit": "count",
            "formatted": f"{int(risk['counts'].get('overstock', 0)):,}",
            "available": True,
            "tone": "warning" if risk["counts"].get("overstock") else "neutral",
        },
        {
            "key": "forecast_demand",
            "label": "Forecasted Demand",
            "value": round2(forecast_demand),
            "unit": "units",
            "formatted": _fmt_number(forecast_demand) if forecast_demand is not None else "—",
            "available": forecast_demand is not None,
            "comparison_label": f"next {horizon} days" if forecast_demand is not None else None,
            "note": None if forecast_demand is not None else "Run a demand forecast to populate this KPI.",
        },
    ]

    demo_rows = int(current.get("demo_rows") or 0)
    demo_share = round(demo_rows / rows_count * 100, 1) if rows_count else None

    return {
        "period": {
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "label": human_period(start.isoformat() if start else None, end.isoformat() if end else None),
            "previous_start": prev_start.isoformat() if prev_start else None,
            "previous_end": prev_end.isoformat() if prev_end else None,
            "active_days": int(current.get("active_days") or 0),
        },
        "filters": filters_dict(start, end, category, product_id, data_source),
        "cards": cards,
        "data_source": data_source or ("demo" if rows_count and demo_rows == rows_count else "actual"),
        "has_data": rows_count > 0,
        "demo_share_pct": demo_share,
        "generated_at": utcnow_iso(),
        "risk_counts": risk["counts"],
        "inventory_value": inventory_value,
    }


# ------------------------------------------------------------------ dashboard
def build_dashboard(
    db: Database,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    product_id: int | None = None,
    data_source: str | None = None,
    granularity: str | None = None,
) -> dict[str, Any]:
    settings = catalog.get_settings_map(db)
    kpis = compute_kpis(
        db,
        start_date=start_date,
        end_date=end_date,
        category=category,
        product_id=product_id,
        data_source=data_source,
        settings=settings,
    )
    start, end = resolve_period(start_date, end_date, data_source, db)
    span_days = (end - start).days + 1 if start and end else 0
    if granularity is None:
        granularity = "month" if span_days > 120 else "week" if span_days > 21 else "day"

    base = {
        "start_date": start,
        "end_date": end,
        "category": category,
        "product_id": product_id,
        "data_source": data_source,
    }
    series = sales_repo.time_series(db, granularity=granularity, **base)
    categories = sales_repo.by_category(db, **base)
    total_cat_revenue = sum(float(row["revenue"]) for row in categories) or 1.0
    category_rows = [
        {
            "category": row["category"],
            "revenue": round2(float(row["revenue"])) or 0.0,
            "units": round2(float(row["units"])) or 0.0,
            "share": round(float(row["revenue"]) / total_cat_revenue * 100, 1),
        }
        for row in categories
    ]

    ranked = sales_repo.by_product(db, **base)
    abc = assign_abc(ranked)
    top_products = [
        _product_row(row, abc.get(int(row["product_id"]))) for row in ranked[:8]
    ]
    low_products = [
        _product_row(row, abc.get(int(row["product_id"])))
        for row in sorted(ranked, key=lambda item: float(item["units"]))[:8]
    ]

    run = forecasts.latest_run(db, data_source=data_source)
    forecast_cov = forecasts.forecast_totals(db, run["id"]) if run else {}
    inventory_map = inventory_repo.get_inventory_map(db)
    from app.services.inventory_logic import assess_risks, stock_vs_forecast_payload

    risk = assess_risks(
        db,
        inventory_map=inventory_map,
        forecast_cov=forecast_cov,
        category=category,
        product_id=product_id,
        data_source=data_source,
        settings=settings,
    )

    return {
        "kpis": kpis,
        "granularity": granularity,
        "sales_over_time": [
            {
                "period": row["period"],
                "revenue": round2(float(row["revenue"])) or 0.0,
                "units": round2(float(row["units"])) or 0.0,
                "orders": int(row["orders"] or 0),
            }
            for row in series
        ],
        "revenue_by_category": category_rows,
        "top_products": top_products,
        "low_products": low_products,
        "stock_vs_forecast": stock_vs_forecast_payload(risk, limit=12),
        "inventory_risk": {
            "counts": risk["counts"],
            "items": risk["items"][:12],
            "summary": risk["summary"],
            "forecast_run_id": run["id"] if run else None,
            "demand_source": "forecast" if run else "trailing-demand",
        },
        "forecast_available": bool(run),
        "forecast_run": (
            {
                "id": run["id"],
                "horizon_days": run["horizon_days"],
                "model_used": run["model_used"],
                "created_at": run["created_at"],
                "data_source": run["data_source"],
                "summary_metrics": run.get("summary_metrics"),
            }
            if run
            else None
        ),
        "onboarding": onboarding_state(db),
    }


def _product_row(row: dict[str, Any], abc_entry: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "product_id": int(row["product_id"]),
        "sku": row["sku"],
        "name": row["name"],
        "category": row.get("category"),
        "units": round2(float(row["units"])) or 0.0,
        "revenue": round2(float(row["revenue"])) or 0.0,
        "orders": int(row["orders"] or 0),
        "avg_price": round2(row.get("avg_price")),
        "abc_class": abc_entry["abc_class"] if abc_entry else None,
        "share_of_revenue": round(float(row["revenue"]) / max(1.0, abc_entry["total_revenue"]) * 100, 2)
        if abc_entry
        else None,
    }


def assign_abc(rows: Iterable[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """ABC classification on cumulative revenue contribution (Pareto)."""
    ordered = sorted(rows, key=lambda item: float(item["revenue"]), reverse=True)
    total = sum(float(row["revenue"]) for row in ordered)
    result: dict[int, dict[str, Any]] = {}
    cumulative = 0.0
    for row in ordered:
        revenue = float(row["revenue"])
        cumulative += revenue
        share = (cumulative / total * 100) if total else 0.0
        abc_class = "A" if share <= 80 else "B" if share <= 95 else "C"
        result[int(row["product_id"])] = {
            "abc_class": abc_class,
            "cumulative_share": round(share, 2),
            "total_revenue": total,
        }
    return result


def onboarding_state(db: Database) -> dict[str, Any]:
    counts = catalog.data_source_counts(db)
    products = catalog.count_products(db)
    batches = sales_repo.list_import_batches(db, limit=1)
    steps = [
        {
            "key": "import",
            "label": "Import sales history",
            "complete": (counts["actual"] + counts["demo"]) > 0,
            "hint": "Upload a CSV/XLSX file, or load the labelled demo dataset.",
        },
        {
            "key": "inventory",
            "label": "Review inventory levels",
            "complete": products > 0,
            "hint": "Set stock, lead times and reorder rules per product.",
        },
        {
            "key": "forecast",
            "label": "Generate a demand forecast",
            "complete": forecasts.latest_run(db) is not None,
            "hint": "A 14-day forecast drives the reorder recommendations.",
        },
        {
            "key": "reorder",
            "label": "Approve a reorder draft",
            "complete": bool(
                db.scalar("SELECT COUNT(*) AS c FROM reorder_recommendations WHERE status <> 'pending'", None, 0)
            ),
            "hint": "Approve recommendations to create purchase drafts.",
        },
    ]
    return {
        "steps": steps,
        "completed": sum(1 for step in steps if step["complete"]),
        "total": len(steps),
        "has_import_batch": bool(batches),
    }


# ------------------------------------------------------------- performance view
def product_performance(
    db: Database,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    product_id: int | None = None,
    data_source: str | None = None,
) -> dict[str, Any]:
    start, end = resolve_period(start_date, end_date, data_source, db)
    prev_start, prev_end = previous_period(start, end)
    base = {
        "start_date": start,
        "end_date": end,
        "category": category,
        "product_id": product_id,
        "data_source": data_source,
    }
    rows = sales_repo.by_product(db, **base)
    abc = assign_abc(rows)
    prev_rows = {
        int(row["product_id"]): row
        for row in sales_repo.by_product(
            db,
            start_date=prev_start,
            end_date=prev_end,
            category=category,
            product_id=product_id,
            data_source=data_source,
        )
    }
    inventory_map = inventory_repo.get_inventory_map(db)
    demand = sales_repo.demand_stats(db, start_date=start, end_date=end, data_source=data_source)
    today = date.today()

    items: list[dict[str, Any]] = []
    for row in rows:
        pid = int(row["product_id"])
        revenue = float(row["revenue"])
        units = float(row["units"])
        abc_entry = abc.get(pid, {})
        previous = prev_rows.get(pid, {})
        previous_revenue = float(previous["revenue"]) if previous else None
        growth = _change(revenue, previous_revenue) if previous_revenue not in (None, 0) else None

        record = inventory_map.get(pid, {})
        unit_cost = record.get("unit_cost") if record else row.get("unit_cost")
        cost_available = unit_cost is not None and float(unit_cost) > 0 and units > 0
        avg_price = safe_divide(revenue, units)
        gross_margin = (
            round((float(avg_price) - float(unit_cost)) * units, 2)
            if cost_available and avg_price is not None
            else None
        )
        gross_margin_pct = (
            round((float(avg_price) - float(unit_cost)) / float(avg_price) * 100, 2)
            if cost_available and avg_price
            else None
        )

        stat = demand.get(pid)
        variability = round(stat["cv"], 3) if stat and stat.get("cv") is not None else None
        last_sale = row.get("last_sale_date")
        days_since = (
            (today - date.fromisoformat(str(last_sale))).days if last_sale else None
        )
        stock = float(record.get("current_stock") or 0) if record else None
        daily = stat["mean"] if stat else None
        days_of_cover = round(stock / daily, 1) if stock is not None and daily else None

        items.append(
            {
                "product_id": pid,
                "sku": row["sku"],
                "name": row["name"],
                "category": row.get("category"),
                "units": round2(units) or 0.0,
                "revenue": round2(revenue) or 0.0,
                "orders": int(row["orders"] or 0),
                "avg_price": round2(avg_price),
                "share_of_revenue": round(revenue / max(1.0, abc_entry.get("total_revenue", 1)) * 100, 2),
                "cumulative_share": abc_entry.get("cumulative_share"),
                "abc_class": abc_entry.get("abc_class"),
                "growth_pct": growth,
                "previous_revenue": round2(previous_revenue),
                "gross_margin": gross_margin,
                "gross_margin_pct": gross_margin_pct,
                "cost_data_available": bool(cost_available),
                "demand_variability": variability,
                "variability_label": (
                    None
                    if variability is None
                    else "very volatile"
                    if variability > 1.0
                    else "volatile"
                    if variability > 0.5
                    else "steady"
                ),
                "days_since_last_sale": days_since,
                "slow_moving": bool(
                    (days_since is not None and days_since > 30)
                    or (days_of_cover is not None and days_of_cover > 90)
                ),
                "current_stock": stock,
                "days_of_cover": days_of_cover,
            }
        )

    items.sort(key=lambda item: item["revenue"], reverse=True)
    abc_summary = [
        {
            "abc_class": cls,
            "products": sum(1 for item in items if item["abc_class"] == cls),
            "revenue": round2(sum(item["revenue"] for item in items if item["abc_class"] == cls)) or 0.0,
            "units": round2(sum(item["units"] for item in items if item["abc_class"] == cls)) or 0.0,
        }
        for cls in ("A", "B", "C")
    ]
    category_summary: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item["category"] or "Uncategorised"
        bucket = category_summary.setdefault(
            key, {"category": key, "products": 0, "units": 0.0, "revenue": 0.0, "margin": 0.0, "cost_known": 0}
        )
        bucket["products"] += 1
        bucket["units"] += item["units"]
        bucket["revenue"] += item["revenue"]
        if item["gross_margin"] is not None:
            bucket["margin"] += item["gross_margin"]
            bucket["cost_known"] += 1

    return {
        "period": {
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
        },
        "compare_period": {
            "start_date": prev_start.isoformat() if prev_start else None,
            "end_date": prev_end.isoformat() if prev_end else None,
        },
        "items": items,
        "abc_summary": abc_summary,
        "category_summary": [
            {
                **bucket,
                "units": round2(bucket["units"]),
                "revenue": round2(bucket["revenue"]),
                "margin": round2(bucket["margin"]) if bucket["cost_known"] else None,
            }
            for bucket in sorted(category_summary.values(), key=lambda b: b["revenue"], reverse=True)
        ],
        "flags": {
            "slow_moving": [item["name"] for item in items if item["slow_moving"]][:20],
            "best_sellers": [item["name"] for item in items[:5]],
            "worst_sellers": [item["name"] for item in sorted(items, key=lambda i: i["units"])[:5]],
            "missing_cost_products": sum(1 for item in items if not item["cost_data_available"]),
            "negative_growth_products": sum(
                1 for item in items if item["growth_pct"] is not None and item["growth_pct"] < 0
            ),
        },
    }


def product_history(
    db: Database,
    product_id: int,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    data_source: str | None = None,
    granularity: str = "day",
) -> list[dict[str, Any]]:
    where, params = sales_repo.build_filters(
        product_id=product_id,
        start_date=start_date,
        end_date=end_date,
        data_source=data_source,
    )
    period = {
        "week": "strftime('%Y-W%W', s.sale_date)",
        "month": "strftime('%Y-%m', s.sale_date)",
    }.get(granularity, "s.sale_date")
    rows = db.query(
        f"""
        SELECT {period} AS period,
               COALESCE(SUM(s.quantity), 0) AS units,
               COALESCE(SUM(s.revenue), 0) AS revenue
        FROM sales_records s
        JOIN products p ON p.id = s.product_id
        {where}
        GROUP BY period
        ORDER BY period
        """,
        params,
    )
    return [
        {
            "period": row["period"],
            "units": round2(float(row["units"])) or 0.0,
            "revenue": round2(float(row["revenue"])) or 0.0,
        }
        for row in rows
    ]
