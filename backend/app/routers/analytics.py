"""Sales analytics, KPI and dashboard endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import Database, get_db
from app.repositories import catalog, sales as sales_repo
from app.routers.deps import DateFilters
from app.schemas import DashboardResponse, KpiResponse, PerformanceResponse
from app.services import analytics

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/kpis", response_model=KpiResponse, summary="Executive KPI cards")
def get_kpis(filters: DateFilters = Depends(), db: Database = Depends(get_db)) -> dict[str, Any]:
    return analytics.compute_kpis(db, **filters.as_kwargs())


@router.get("/dashboard", response_model=DashboardResponse, summary="Full dashboard payload")
def get_dashboard(
    filters: DateFilters = Depends(),
    granularity: str | None = Query(default=None, pattern="^(day|week|month)$"),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    return analytics.build_dashboard(db, granularity=granularity, **filters.as_kwargs())


@router.get("/sales", summary="Sales time series, category split and product ranking")
def get_sales(
    filters: DateFilters = Depends(),
    granularity: str = Query(default="day", pattern="^(day|week|month)$"),
    limit: int = Query(default=20, ge=1, le=200),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    start, end = analytics.resolve_period(filters.start_date, filters.end_date, filters.data_source, db)
    base = {
        "start_date": start,
        "end_date": end,
        "category": filters.category,
        "product_id": filters.product_id,
        "data_source": filters.data_source,
    }
    series = sales_repo.time_series(db, granularity=granularity, **base)
    categories = sales_repo.by_category(db, **base)
    products = sales_repo.by_product(db, **base)
    abc = analytics.assign_abc(products)
    total_revenue = sum(float(row["revenue"]) for row in categories) or 1.0
    return {
        "period": {
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "granularity": granularity,
        },
        "totals": sales_repo.totals(db, **base),
        "series": series,
        "categories": [
            {
                **row,
                "revenue": float(row["revenue"]),
                "units": float(row["units"]),
                "share": round(float(row["revenue"]) / total_revenue * 100, 1),
            }
            for row in categories
        ],
        "products": [
            {
                **row,
                "revenue": float(row["revenue"]),
                "units": float(row["units"]),
                "abc_class": (abc.get(int(row["product_id"])) or {}).get("abc_class"),
            }
            for row in products[:limit]
        ],
        "product_count": len(products),
    }


@router.get("/performance", response_model=PerformanceResponse, summary="Product performance analytics")
def get_performance(filters: DateFilters = Depends(), db: Database = Depends(get_db)) -> dict[str, Any]:
    return analytics.product_performance(db, **filters.as_kwargs())


@router.get("/products/{product_id}/history", summary="Historical demand for one product")
def get_product_history(
    product_id: int,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    granularity: str = Query(default="day", pattern="^(day|week|month)$"),
    data_source: str | None = Query(default=None, pattern="^(actual|demo)$"),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    product = catalog.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {product_id} was not found.")
    from app.utils import parse_iso_date

    start = parse_iso_date(start_date)
    end = parse_iso_date(end_date)
    history = analytics.product_history(
        db,
        product_id,
        start_date=start,
        end_date=end,
        data_source=data_source,
        granularity=granularity,
    )
    return {
        "product_id": product_id,
        "sku": product["sku"],
        "name": product["name"],
        "category": product.get("category"),
        "granularity": granularity,
        "history": history,
        "total_units": sum(point["units"] for point in history),
        "total_revenue": sum(point["revenue"] for point in history),
    }
