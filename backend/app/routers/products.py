"""Product master CRUD, categories and suppliers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import Database, get_db
from app.repositories import audit, catalog
from app.schemas import MessageResponse, PaginatedProducts, ProductCreate, ProductOut, ProductUpdate, SupplierOut

router = APIRouter(prefix="/api", tags=["Products"])


def _serialise(row: dict[str, Any]) -> dict[str, Any]:
    inventory = None
    if row.get("current_stock") is not None:
        inventory = {
            "product_id": int(row["id"]),
            "current_stock": float(row.get("current_stock") or 0),
            "reorder_threshold": float(row.get("reorder_threshold") or 0),
            "lead_time_days": int(row.get("lead_time_days") or 0),
            "min_order_qty": int(row.get("min_order_qty") or 1),
            "pack_size": int(row.get("pack_size") or 1),
            "safety_stock_days": float(row.get("safety_stock_days") or 0),
            "review_period_days": int(row.get("review_period_days") or 0),
            "target_cover_days": row.get("target_cover_days"),
            "updated_at": row.get("inventory_updated_at"),
        }
    return {
        "id": int(row["id"]),
        "sku": row["sku"],
        "name": row["name"],
        "category": row.get("category"),
        "supplier_id": row.get("supplier_id"),
        "supplier_name": row.get("supplier_name"),
        "unit_cost": row.get("unit_cost"),
        "selling_price": row.get("selling_price"),
        "uom": row.get("uom") or "unit",
        "is_whole_units": bool(row.get("is_whole_units", 1)),
        "is_active": bool(row.get("is_active", 1)),
        "is_demo": bool(row.get("is_demo", 0)),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "inventory": inventory,
    }


@router.get("/products", response_model=PaginatedProducts, summary="List products")
def list_products(
    search: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    sort_by: str = Query(default="name", pattern="^(name|sku|category|created_at|current_stock|reorder_threshold|lead_time_days)$"),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    rows, total = catalog.list_products(
        db, search=search, category=category, page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir
    )
    pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": [_serialise(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


@router.get("/categories", response_model=list[str], summary="Distinct product categories")
def list_categories(db: Database = Depends(get_db)) -> list[str]:
    return catalog.categories(db)


@router.get("/suppliers", response_model=list[SupplierOut], summary="List suppliers")
def list_suppliers(db: Database = Depends(get_db)) -> list[dict[str, Any]]:
    return catalog.list_suppliers(db)


@router.get("/products/{product_id}", response_model=ProductOut, summary="Product detail")
def get_product(product_id: int, db: Database = Depends(get_db)) -> dict[str, Any]:
    row = catalog.get_product(db, product_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Product {product_id} was not found.")
    return _serialise(row)


@router.post("/products", response_model=ProductOut, status_code=201, summary="Create a product")
def create_product(payload: ProductCreate, db: Database = Depends(get_db)) -> dict[str, Any]:
    if catalog.get_product_by_sku(db, payload.sku):
        raise HTTPException(status_code=409, detail=f"A product with SKU '{payload.sku}' already exists.")
    product_id = catalog.create_product(
        db,
        sku=payload.sku,
        name=payload.name,
        category=payload.category,
        supplier_id=payload.supplier_id,
        unit_cost=payload.unit_cost,
        selling_price=payload.selling_price,
        uom=payload.uom,
        is_whole_units=payload.is_whole_units,
    )
    audit.log(
        db,
        action="product.created",
        entity_type="product",
        entity_id=product_id,
        actor="store-manager",
        details={"sku": payload.sku, "name": payload.name},
    )
    return _serialise(catalog.get_product(db, product_id) or {})


@router.patch("/products/{product_id}", response_model=ProductOut, summary="Update a product")
def update_product(product_id: int, payload: ProductUpdate, db: Database = Depends(get_db)) -> dict[str, Any]:
    existing = catalog.get_product(db, product_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Product {product_id} was not found.")
    if payload.sku and payload.sku != existing["sku"]:
        clash = catalog.get_product_by_sku(db, payload.sku)
        if clash:
            raise HTTPException(status_code=409, detail=f"A product with SKU '{payload.sku}' already exists.")
    changed = payload.model_dump(exclude_unset=True)
    if not catalog.update_product(db, product_id, changed):
        raise HTTPException(status_code=400, detail="No supported fields were supplied to update.")
    audit.log(
        db,
        action="product.updated",
        entity_type="product",
        entity_id=product_id,
        actor="store-manager",
        details={"fields": list(changed.keys())},
    )
    return _serialise(catalog.get_product(db, product_id) or {})


@router.delete("/products/{product_id}", response_model=MessageResponse, summary="Deactivate a product")
def delete_product(product_id: int, db: Database = Depends(get_db)) -> dict[str, Any]:
    existing = catalog.get_product(db, product_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Product {product_id} was not found.")
    catalog.delete_product(db, product_id)
    audit.log(
        db,
        action="product.deactivated",
        entity_type="product",
        entity_id=product_id,
        actor="store-manager",
        details={"sku": existing["sku"]},
    )
    return {
        "message": f"Product '{existing['name']}' was deactivated. Historical sales are preserved.",
        "detail": "Reactivate it with PATCH /api/products/{id} and is_active=true.",
    }
