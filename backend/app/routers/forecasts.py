"""Demand forecasting endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import Database, get_db
from app.repositories import forecasts as forecast_repo
from app.schemas import ForecastRequest, ForecastRunDetail, ForecastRunSummary, ProductForecastDetail
from app.services import forecasting
from app.services.forecasting import InsufficientHistory

router = APIRouter(prefix="/api/forecasts", tags=["Demand forecasting"])


@router.get("/models", summary="Forecasting models available in this installation")
def list_models() -> dict[str, Any]:
    available = forecasting.available_models()
    return {
        "available": available,
        "baseline": "seasonal_naive",
        "recommended": [name for name in ("hist_gradient_boosting", "xgboost") if name in available],
        "features": forecasting.FEATURE_COLUMNS,
        "limitations": forecasting.LIMITATIONS,
        "minimum_history_days": forecasting.MIN_BASELINE_DAYS,
    }


@router.post(
    "/run",
    response_model=ForecastRunDetail,
    status_code=201,
    summary="Generate a forecast run",
    responses={422: {"description": "Insufficient history"}},
)
def create_forecast(payload: ForecastRequest, db: Database = Depends(get_db)) -> dict[str, Any]:
    try:
        result = forecasting.run_forecast(
            db,
            horizon_days=payload.horizon_days,
            model=payload.model,
            product_ids=payload.product_ids,
            category=payload.category,
            data_source=payload.data_source,
            missing_day_policy=payload.missing_day_policy,
        )
    except InsufficientHistory as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return forecasting.run_detail(db, int(result["run"]["id"]))


@router.get("/runs", response_model=list[ForecastRunSummary], summary="Forecast run history")
def list_runs(limit: int = Query(default=20, ge=1, le=100), db: Database = Depends(get_db)) -> list[dict[str, Any]]:
    return forecast_repo.list_runs(db, limit=limit)


@router.get("/latest", summary="Latest completed forecast run (or 404)")
def latest_run(
    data_source: str | None = Query(default=None, pattern="^(actual|demo)$"),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    run = forecast_repo.latest_run(db, data_source=data_source)
    if not run:
        raise HTTPException(status_code=404, detail="No completed forecast run exists yet. Generate one first.")
    detail = forecasting.run_detail(db, int(run["id"]))
    # Keep the payload small: the evaluation table is available at /runs/{id}.
    detail.pop("results", None)
    return detail


@router.get("/runs/{run_id}", response_model=ForecastRunDetail, summary="Forecast run detail with metrics")
def get_run(run_id: int, db: Database = Depends(get_db)) -> dict[str, Any]:
    try:
        return forecasting.run_detail(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/runs/{run_id}/products/{product_id}",
    response_model=ProductForecastDetail,
    summary="Per-product history, forecast and metrics",
)
def get_product_forecast(run_id: int, product_id: int, db: Database = Depends(get_db)) -> dict[str, Any]:
    try:
        return forecasting.product_detail(db, run_id, product_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
