"""Shared router dependencies and small helpers."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException, Query

from app.db import Database, get_db
from app.utils import parse_iso_date

__all__ = ["get_db", "Database", "DateFilters", "resolve_filters", "not_found", "bad_request"]


class DateFilters:
    """Common query parameters used by every analytics endpoint."""

    def __init__(
        self,
        start_date: date | None = Query(default=None, description="Inclusive ISO start date (YYYY-MM-DD)"),
        end_date: date | None = Query(default=None, description="Inclusive ISO end date (YYYY-MM-DD)"),
        category: str | None = Query(default=None, description="Filter by product category"),
        product_id: int | None = Query(default=None, ge=1, description="Filter by product id"),
        data_source: str | None = Query(
            default=None,
            pattern="^(actual|demo)$",
            description="Restrict to real imported records (`actual`) or the synthetic demo dataset (`demo`).",
        ),
    ) -> None:
        if start_date and end_date and start_date > end_date:
            raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
        self.start_date = start_date
        self.end_date = end_date
        self.category = category
        self.product_id = product_id
        self.data_source = data_source

    def as_kwargs(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "category": self.category,
            "product_id": self.product_id,
            "data_source": self.data_source,
        }

    def report_filters(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "category": self.category,
            "product_id": self.product_id,
            "data_source": self.data_source,
        }


def resolve_filters(start: str | None, end: str | None) -> tuple[date | None, date | None]:
    start_date = parse_iso_date(start)
    end_date = parse_iso_date(end)
    if start and not start_date:
        raise bad_request(f"'{start}' is not a valid ISO date (expected YYYY-MM-DD).")
    if end and not end_date:
        raise bad_request(f"'{end}' is not a valid ISO date (expected YYYY-MM-DD).")
    if start_date and end_date and start_date > end_date:
        raise bad_request("start_date must be on or before end_date.")
    return start_date, end_date


def not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)
