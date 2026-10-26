"""Data import endpoints: upload, validate, commit, history, reports, template."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from app.config import get_settings
from app.db import Database, get_db
from app.repositories import audit, sales as sales_repo
from app.schemas import (
    ImportBatchOut,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportValidateResponse,
    RevalidateRequest,
)
from app.services import imports as import_service
from app.services.imports import UploadRejected, sample_template_frame, write_validation_report
from app.services.validation import FIELD_LABELS, detect_mapping

router = APIRouter(prefix="/api/imports", tags=["Data import"])


@router.get("/template", summary="Download the sample sales template")
def download_template(format: str = Query(default="csv", pattern="^(csv|xlsx)$")) -> Response:
    frame = sample_template_frame()
    settings = get_settings()
    settings.ensure_directories()
    if format == "csv":
        payload = frame.to_csv(index=False).encode("utf-8")
        return Response(
            content=payload,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="sales_template.csv"'},
        )
    destination = settings.upload_dir / "sales_template.xlsx"
    with __import__("pandas").ExcelWriter(destination, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="sales", index=False)
    return FileResponse(
        destination,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="sales_template.xlsx",
    )


@router.get("/fields", summary="Supported import fields and detected column aliases")
def supported_fields() -> dict[str, Any]:
    return {
        "fields": [
            {"key": key, "label": label, "required": key in {"date", "quantity"} or key in {"sku", "product_name"}}
            for key, label in FIELD_LABELS.items()
        ],
        "required": ["date", "quantity", "sku or product_name"],
        "notes": [
            "Dates accept YYYY-MM-DD, DD-MM-YYYY, MM/DD/YYYY and Excel serial dates.",
            "Negative quantities are rejected unless the absolute-value cleaning rule is enabled.",
            "Rows are deduplicated on (product, date, quantity, unit price).",
        ],
    }


@router.post(
    "/upload",
    response_model=ImportValidateResponse,
    summary="Upload a CSV/XLSX sales file and validate it",
    responses={400: {"description": "Malformed file"}, 413: {"description": "File too large"}, 415: {"description": "Unsupported file type"}},
)
async def upload_sales_file(
    file: UploadFile = File(..., description="CSV or XLSX sales export"),
    data_source: str = Form(default="actual", pattern="^(actual|demo)$"),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    content = await file.read()
    try:
        stored = import_service.save_upload(file.filename, content, file.content_type)
        frame = import_service.read_table(stored["path"], stored["file_type"])
        detected = detect_mapping([str(column) for column in frame.columns])
        report = import_service.validate_upload(
            db,
            filename=stored["filename"],
            file_type=stored["file_type"],
            size_bytes=stored["size_bytes"],
            frame=frame,
            mapping=detected,
            data_source=data_source,
        )
        import_service.promote_upload(report["batch_id"], stored["path"], stored["file_type"])
    except UploadRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    audit.log(
        db,
        action="import.validated",
        entity_type="import_batch",
        entity_id=report["batch_id"],
        actor="data-manager",
        details={"filename": report["filename"], "valid": report["valid_rows"], "invalid": report["invalid_rows"]},
    )
    return report


@router.post(
    "/{batch_id}/revalidate",
    response_model=ImportValidateResponse,
    summary="Re-run validation with a different column mapping or cleaning selection",
)
def revalidate_batch(
    batch_id: int,
    payload: RevalidateRequest | None = None,
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    batch = sales_repo.get_import_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Import batch {batch_id} was not found.")
    path = import_service.stored_file_path(batch_id, batch["file_type"])
    if not path.exists():
        raise HTTPException(
            status_code=410, detail="The stored upload is no longer available; upload the file again."
        )
    try:
        frame = import_service.read_table(path, batch["file_type"])
    except UploadRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    report = import_service.validate_upload(
        db,
        filename=batch["filename"],
        file_type=batch["file_type"],
        size_bytes=int(batch["file_size_bytes"] or 0),
        frame=frame,
        mapping=(payload.mapping if payload and payload.mapping else batch.get("column_mapping")),
        data_source=batch.get("data_source") or "actual",
        apply_cleaning=payload.cleaning if payload else None,
    )
    return report


@router.post(
    "/commit",
    response_model=ImportCommitResponse,
    summary="Import the validated rows into the database",
    responses={409: {"description": "Batch already imported"}, 422: {"description": "No valid rows"}},
)
def commit_import(payload: ImportCommitRequest, db: Database = Depends(get_db)) -> dict[str, Any]:
    try:
        result = import_service.commit_upload(
            db,
            batch_id=payload.batch_id,
            mapping=payload.mapping,
            apply_cleaning=payload.apply_cleaning,
            skip_duplicates=payload.skip_duplicates,
            data_source=payload.data_source,
        )
    except UploadRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return result


@router.get("/history", response_model=list[ImportBatchOut], summary="Import history")
def import_history(limit: int = Query(default=50, ge=1, le=200), db: Database = Depends(get_db)) -> list[dict[str, Any]]:
    return sales_repo.list_import_batches(db, limit=limit)


@router.get("/{batch_id}", summary="Import batch detail")
def import_detail(batch_id: int, db: Database = Depends(get_db)) -> dict[str, Any]:
    batch = sales_repo.get_import_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Import batch {batch_id} was not found.")
    return batch


@router.get("/{batch_id}/report", summary="Download the validation report (XLSX)")
def download_validation_report(batch_id: int, db: Database = Depends(get_db)) -> FileResponse:
    batch = sales_repo.get_import_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Import batch {batch_id} was not found.")
    if not import_service.report_path(batch_id).exists():
        raise HTTPException(
            status_code=404, detail="No validation report is stored for this batch (it may pre-date this feature)."
        )
    settings = get_settings()
    destination = settings.upload_dir / f"validation_report_batch_{batch_id}.xlsx"
    try:
        write_validation_report(db, batch_id, destination)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="The validation report could not be generated.") from exc
    return FileResponse(
        destination,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=Path(destination).name,
    )
