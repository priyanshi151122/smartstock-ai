"""Reorder recommendation endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import Database, get_db
from app.repositories import audit, forecasts as forecast_repo
from app.schemas import RecommendationDecision, RecommendationGenerateRequest, RecommendationOut
from app.services import inventory_logic

router = APIRouter(prefix="/api/recommendations", tags=["Reorder recommendations"])


@router.get("", summary="List reorder recommendations")
def list_recommendations(
    status: str | None = Query(default=None, pattern="^(pending|approved|dismissed)$"),
    risk_level: str | None = Query(default=None, pattern="^(stockout|high|medium|low|overstock|unknown)$"),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
    sort_by: str = Query(
        default="risk_priority",
        pattern="^(risk_priority|product_name|sku|current_stock|forecast_demand|safety_stock|reorder_point|suggested_quantity|estimated_cost|lead_time_days|coverage_days|created_at)$",
    ),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    rows, total = forecast_repo.list_recommendations(
        db,
        status=status,
        risk_level=risk_level,
        category=category,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    counts = {
        row["status"]: int(row["c"])
        for row in db.query(
            "SELECT status, COUNT(*) AS c FROM reorder_recommendations GROUP BY status"
        )
    }
    pending_cost = db.scalar(
        "SELECT SUM(estimated_cost) AS s FROM reorder_recommendations WHERE status = 'pending'", None, 0
    )
    pending_units = db.scalar(
        "SELECT SUM(suggested_quantity) AS s FROM reorder_recommendations WHERE status = 'pending'", None, 0
    )
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "counts": counts,
        "pending_cost": float(pending_cost or 0),
        "pending_units": float(pending_units or 0),
    }


@router.post("/generate", status_code=201, summary="Rebuild recommendations from the latest forecast")
def generate_recommendations(
    payload: RecommendationGenerateRequest, db: Database = Depends(get_db)
) -> dict[str, Any]:
    try:
        result = inventory_logic.generate_recommendations(
            db,
            run_id=payload.run_id,
            horizon_days=payload.horizon_days,
            category=payload.category,
            service_level_z=payload.service_level_z,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit.log(
        db,
        action="recommendations.generated",
        entity_type="reorder_recommendations",
        entity_id=result.get("run_id"),
        actor="planner",
        details=result,
    )
    return result


@router.get("/{reco_id}", response_model=RecommendationOut, summary="Recommendation detail")
def get_recommendation(reco_id: int, db: Database = Depends(get_db)) -> dict[str, Any]:
    row = forecast_repo.get_recommendation(db, reco_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Recommendation {reco_id} was not found.")
    return row


@router.post("/{reco_id}/decision", response_model=RecommendationOut, summary="Approve or dismiss a recommendation")
def decide_recommendation(
    reco_id: int, payload: RecommendationDecision, db: Database = Depends(get_db)
) -> dict[str, Any]:
    row = forecast_repo.get_recommendation(db, reco_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Recommendation {reco_id} was not found.")
    if row["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Recommendation {reco_id} was already {row['status']} — decisions are final for this draft.",
        )
    order_draft_ref = None
    if payload.status == "approved":
        order_draft_ref = f"PO-DRAFT-{reco_id:05d}"
        audit.log(
            db,
            action="purchase_order_draft.created",
            entity_type="purchase_order_draft",
            entity_id=order_draft_ref,
            actor=payload.actor,
            details={
                "product_id": row["product_id"],
                "sku": row["sku"],
                "quantity": row["suggested_quantity"],
                "supplier": row.get("supplier_name"),
                "estimated_cost": row.get("estimated_cost"),
                "note": "Draft only — no order has been sent to the supplier.",
            },
        )
    forecast_repo.decide_recommendation(
        db,
        reco_id,
        status=payload.status,
        actor=payload.actor,
        note=payload.note,
        order_draft_ref=order_draft_ref,
    )
    audit.log(
        db,
        action=f"recommendation.{payload.status}",
        entity_type="reorder_recommendation",
        entity_id=reco_id,
        actor=payload.actor,
        details={
            "product_id": row["product_id"],
            "quantity": row["suggested_quantity"],
            "note": payload.note,
            "order_draft_ref": order_draft_ref,
        },
    )
    return forecast_repo.get_recommendation(db, reco_id) or {}
