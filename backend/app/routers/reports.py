"""Report generation and download endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.db import Database, get_db
from app.repositories import audit
from app.schemas import ReportFile, ReportRequest
from app.services import reports as report_service
from app.services.reports import ReportError, safe_report_path

MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}

router = APIRouter(prefix="/api/reports", tags=["Reports & exports"])


@router.get("/types", summary="Available report types and formats")
def report_types() -> dict[str, Any]:
    return {
        "types": [
            {"key": key, "label": label}
            for key, label in report_service.REPORT_LABELS.items()
        ],
        "formats": ["csv", "xlsx", "pdf"],
        "notes": [
            "Exports use the same filters as the dashboards, so the file matches what you see.",
            "CSV exports contain the primary sheet; XLSX contains every sheet of the report.",
            "PDF exports include the reporting period, generation timestamp and summary charts.",
        ],
    }


@router.post("", response_model=ReportFile, status_code=201, summary="Generate a report file")
def generate_report(payload: ReportRequest, db: Database = Depends(get_db)) -> dict[str, Any]:
    filters = {
        "start_date": payload.start_date.isoformat() if payload.start_date else None,
        "end_date": payload.end_date.isoformat() if payload.end_date else None,
        "category": payload.category,
        "product_id": payload.product_id,
        "data_source": payload.data_source,
        "run_id": payload.run_id,
    }
    try:
        result = report_service.generate_report(
            db,
            report_type=payload.report_type,
            file_format=payload.file_format,
            filters=filters,
        )
    except ReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit.log(
        db,
        action="report.generated",
        entity_type="report",
        entity_id=result["filename"],
        actor="store-manager",
        details={"report_type": payload.report_type, "format": payload.file_format, "filters": filters},
    )
    return result


@router.get("", response_model=list[ReportFile], summary="Recently generated reports")
def list_reports(limit: int = Query(default=25, ge=1, le=200)) -> list[dict[str, Any]]:
    return report_service.list_reports(limit=limit)


@router.get("/download/{filename}", summary="Download a generated report")
def download_report(filename: str) -> FileResponse:
    try:
        path = safe_report_path(filename)
    except ReportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    media_type = MEDIA_TYPES.get(path.suffix.lstrip("."), "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=path.name)
