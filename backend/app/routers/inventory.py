"""Inventory endpoints: listing, configuration, stock adjustments, movement ledger."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import Database, get_db
from app.repositories import audit, catalog, inventory as inventory_repo
from app.schemas import InventoryListResponse, InventoryUpdate, InventoryRow, StockAdjustment, StockMovementOut
from app.services import inventory_logic
from app.utils import round2

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])


@router.get("", response_model=InventoryListResponse, summary="Inventory with risk assessment")
def list_inventory(
    search: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    sort_by: str = Query(default="name", pattern="^(name|sku|category|current_stock|reorder_threshold|lead_time_days|value)$"),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    data_source: str | None = Query(default=None, pattern="^(actual|demo)$"),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    return inventory_logic.inventory_overview(
        db,
        search=search,
        category=category,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        data_source=data_source,
    )


@router.get("/summary", summary="Inventory risk summary counters")
def inventory_summary(
    data_source: str | None = Query(default=None, pattern="^(actual|demo)$"),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    from app.repositories import forecasts as forecast_repo

    run = forecast_repo.latest_run(db, data_source=data_source)
    forecast_cov = forecast_repo.forecast_totals(db, run["id"]) if run else {}
    risk = inventory_logic.assess_risks(db, forecast_cov=forecast_cov, data_source=data_source)
    return {
        "counts": risk["counts"],
        "summary": risk["summary"],
        "demand_source": risk["demand_source"],
        "forecast_run_id": run["id"] if run else None,
    }


@router.get("/movements", response_model=list[StockMovementOut], summary="Stock movement ledger")
def list_movements(
    product_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Database = Depends(get_db),
) -> list[dict[str, Any]]:
    rows, _total = inventory_repo.list_movements(db, product_id=product_id, limit=limit, offset=offset)
    return rows


@router.get("/{product_id}", response_model=InventoryRow, summary="Inventory for one product")
def get_inventory(product_id: int, db: Database = Depends(get_db)) -> dict[str, Any]:
    record = inventory_repo.get_inventory(db, product_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No inventory record exists for product {product_id}.")
    overview = inventory_logic.inventory_overview(db, page=1, page_size=2000)
    match = next(
        (item for item in overview["items"] if item["product_id"] == product_id),
        None,
    )
    if match:
        return match
    stock = float(record.get("current_stock") or 0)
    return {
        "product_id": product_id,
        "sku": record["sku"],
        "name": record["name"],
        "category": record.get("category"),
        "supplier_name": record.get("supplier_name"),
        "current_stock": round2(stock),
        "reorder_threshold": round2(float(record.get("reorder_threshold") or 0)),
        "lead_time_days": int(record.get("lead_time_days") or 0),
        "min_order_qty": int(record.get("min_order_qty") or 1),
        "pack_size": int(record.get("pack_size") or 1),
        "safety_stock_days": round2(float(record.get("safety_stock_days") or 0)),
        "review_period_days": int(record.get("review_period_days") or 0),
        "target_cover_days": record.get("target_cover_days"),
        "unit_cost": round2(record.get("unit_cost")),
        "selling_price": round2(record.get("selling_price")),
        "stock_value": round2(stock * float(record["unit_cost"])) if record.get("unit_cost") else None,
        "recent_daily_demand": None,
        "days_of_cover": None,
        "risk_level": "unknown",
        "risk_reason": None,
        "updated_at": record.get("updated_at"),
    }


@router.patch("/{product_id}", response_model=InventoryRow, summary="Update inventory configuration")
def update_inventory(
    product_id: int, payload: InventoryUpdate, db: Database = Depends(get_db)
) -> dict[str, Any]:
    if not catalog.get_product(db, product_id):
        raise HTTPException(status_code=404, detail=f"Product {product_id} was not found.")
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=422, detail="No inventory fields were supplied.")
    previous = inventory_repo.get_inventory(db, product_id) or {}
    inventory_repo.ensure_inventory_row(db, product_id)
    if "current_stock" in fields and float(fields["current_stock"]) != float(previous.get("current_stock") or 0):
        # Route stock level changes through the audited movement ledger.
        inventory_repo.set_stock(
            db,
            product_id,
            float(fields.pop("current_stock")),
            movement_type="adjustment",
            reason="Stock level updated via inventory settings",
            actor="store-manager",
            reference="inventory:patch",
        )
    inventory_repo.update_inventory(db, product_id, fields)
    audit.log(
        db,
        action="inventory.updated",
        entity_type="inventory",
        entity_id=product_id,
        actor="store-manager",
        details={"fields": list(fields.keys())},
    )
    return get_inventory(product_id, db)


@router.post("/{product_id}/adjust", response_model=InventoryRow, summary="Adjust stock (audited)")
def adjust_stock(product_id: int, payload: StockAdjustment, db: Database = Depends(get_db)) -> dict[str, Any]:
    record = inventory_repo.get_inventory(db, product_id)
    if not record:
        if not catalog.get_product(db, product_id):
            raise HTTPException(status_code=404, detail=f"Product {product_id} was not found.")
        inventory_repo.ensure_inventory_row(db, product_id)
        record = inventory_repo.get_inventory(db, product_id) or {}
    current = float(record.get("current_stock") or 0)
    allowed, message = inventory_repo.adjustments_allowed(current, payload.quantity_delta)
    if not allowed:
        raise HTTPException(status_code=422, detail=message)
    new_stock = current + payload.quantity_delta
    inventory_repo.set_stock(
        db,
        product_id,
        new_stock,
        movement_type="adjustment",
        reason=payload.reason,
        actor=payload.actor,
        reference=payload.reference,
    )
    audit.log(
        db,
        action="inventory.adjusted",
        entity_type="inventory",
        entity_id=product_id,
        actor=payload.actor,
        details={
            "previous_stock": current,
            "delta": payload.quantity_delta,
            "new_stock": new_stock,
            "reason": payload.reason,
        },
    )
    return get_inventory(product_id, db)


@router.get("/{product_id}/movements", response_model=list[StockMovementOut], summary="Movements for a product")
def product_movements(
    product_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    db: Database = Depends(get_db),
) -> list[dict[str, Any]]:
    rows, _total = inventory_repo.list_movements(db, product_id=product_id, limit=limit)
    return rows
