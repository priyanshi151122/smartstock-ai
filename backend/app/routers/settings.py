"""Application settings, audit trail and demo-data management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings as get_app_settings
from app.db import Database, get_db
from app.repositories import audit, catalog, forecasts as forecast_repo, sales as sales_repo
from app.schemas import AuditLogOut, SettingsOut, SettingsUpdate
from app.services import demo

router = APIRouter(prefix="/api", tags=["Settings & administration"])


@router.get("/settings", response_model=SettingsOut, summary="Read application settings")
def read_settings(db: Database = Depends(get_db)) -> dict[str, Any]:
    stored = catalog.get_settings_map(db)
    counts = catalog.data_source_counts(db)
    settings = get_app_settings()
    return {
        "store_name": stored["store_name"],
        "currency": stored["currency"],
        "currency_symbol": stored["currency_symbol"],
        "currency_locale": stored["currency_locale"],
        "default_horizon_days": int(stored["default_horizon_days"]),
        "service_level_z": float(stored["service_level_z"]),
        "default_theme": stored["default_theme"],
        "demo_data_available": counts["demo"] > 0,
        "demo_rows": counts["demo"],
        "actual_rows": counts["actual"],
        "products": catalog.count_products(db),
        "max_upload_mb": settings.max_upload_mb,
        "environment": settings.environment,
        "app_version": settings.app_version,
        "database_dialect": db.dialect,
    }


@router.put("/settings", response_model=SettingsOut, summary="Update application settings")
def update_settings(payload: SettingsUpdate, db: Database = Depends(get_db)) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="No settings were supplied.")
    catalog.set_settings(db, values)
    audit.log(
        db,
        action="settings.updated",
        entity_type="app_settings",
        actor="store-manager",
        details=values,
    )
    return read_settings(db)


@router.get("/audit-logs", summary="Audit trail of stock, import and recommendation events")
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    entity_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    rows, total = audit.list_logs(
        db, limit=limit, offset=offset, entity_type=entity_type, action=action
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/meta", summary="Reference data for filters and onboarding")
def get_meta(db: Database = Depends(get_db)) -> dict[str, Any]:
    counts = catalog.data_source_counts(db)
    first, last = sales_repo.distinct_dates(db)
    run = forecast_repo.latest_run(db)
    return {
        "categories": catalog.categories(db),
        "products": catalog.count_products(db),
        "sales_rows": counts["actual"] + counts["demo"],
        "demo_rows": counts["demo"],
        "actual_rows": counts["actual"],
        "date_range": {"start": first, "end": last},
        "latest_forecast_run": run["id"] if run else None,
        "latest_forecast_at": run["created_at"] if run else None,
        "onboarding": __import__(
            "app.services.analytics", fromlist=["onboarding_state"]
        ).onboarding_state(db),
        "demo_available": True,
    }


@router.post("/demo/load", summary="Load the labelled synthetic demo dataset")
def load_demo(
    reset: bool = Query(default=True, description="Remove previously loaded demo rows first"),
    seed: int = Query(default=demo.DEMO_SEED, ge=1, le=10_000_000),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    return demo.seed_demo_data(db, reset=reset, seed=seed)


@router.post("/demo/clear", summary="Remove the synthetic demo dataset")
def clear_demo(db: Database = Depends(get_db)) -> dict[str, Any]:
    return demo.clear_demo_data(db)
