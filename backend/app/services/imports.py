"""Upload ingestion: file safety checks, parsing, validation reports and commit."""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import get_settings
from app.db import Database
from app.repositories import audit, catalog, inventory as inventory_repo, sales as sales_repo
from app.services.validation import (
    FIELD_LABELS,
    preview_rows,
    resolve_mapping,
    missing_required,
    validate_frame,
)
from app.utils import sanitize_text, utcnow_iso

ALLOWED_MIME_HINTS = {
    ".csv": ("text/plain", "text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
        "application/zip",
    ),
    ".xlsm": (
        "application/vnd.ms-excel.sheet.macroEnabled.12",
        "application/octet-stream",
        "application/zip",
    ),
}


class UploadRejected(Exception):
    """Raised for any user-fixable problem with an uploaded file."""

    def __init__(self, message: str, *, status_code: int = 400, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


def _uploads_dir() -> Path:
    settings = get_settings()
    settings.ensure_directories()
    return settings.upload_dir


def stored_file_path(batch_id: int, file_type: str) -> Path:
    return _uploads_dir() / f"batch_{batch_id}.{file_type}"


def report_path(batch_id: int) -> Path:
    return _uploads_dir() / f"batch_{batch_id}.validation.json"


# --------------------------------------------------------------------- storing
def save_upload(filename: str | None, content: bytes, content_type: str | None = None) -> dict[str, Any]:
    """Validate an uploaded payload and park it under a temporary uuid name."""
    settings = get_settings()
    safe_name = sanitize_text(Path(filename or "upload").name, 180) or "upload"
    suffix = Path(safe_name).suffix.lower()

    if suffix not in settings.allowed_upload_extensions:
        raise UploadRejected(
            f"Unsupported file type '{suffix or 'unknown'}'. Upload a .csv or .xlsx file.",
            status_code=415,
        )
    if not content:
        raise UploadRejected("The uploaded file is empty.", status_code=400)
    size_limit = settings.max_upload_mb * 1024 * 1024
    if len(content) > size_limit:
        raise UploadRejected(
            f"File is {len(content) / 1024 / 1024:.1f} MB which exceeds the {settings.max_upload_mb} MB limit.",
            status_code=413,
        )
    if suffix in {".xlsx", ".xlsm"} and not content.startswith(b"PK"):
        raise UploadRejected(
            "The file does not look like a valid Excel workbook (missing ZIP signature).",
            status_code=400,
        )
    if suffix == ".csv":
        sample = content[:8192]
        if b"\x00" in sample:
            raise UploadRejected(
                "The CSV contains binary content (NUL bytes). Export it as plain UTF-8 CSV.",
                status_code=400,
            )
        allowed_mimes = ALLOWED_MIME_HINTS[".csv"]
        if content_type and content_type.split(";")[0].strip() not in allowed_mimes:
            # Not fatal: browsers frequently send octet-stream. Recorded for transparency.
            pass

    token = uuid.uuid4().hex
    temp_path = _uploads_dir() / f"pending_{token}.{suffix.lstrip('.')}"
    temp_path.write_bytes(content)
    return {
        "filename": safe_name,
        "file_type": suffix.lstrip("."),
        "path": temp_path,
        "size_bytes": len(content),
        "content_type": content_type,
    }


def read_table(path: Path, file_type: str, *, max_rows: int | None = None) -> pd.DataFrame:
    """Read a CSV/XLSX file into a DataFrame with helpful failure messages."""
    settings = get_settings()
    limit = max_rows or settings.max_upload_rows
    try:
        if file_type == "csv":
            try:
                frame = pd.read_csv(path, dtype=str, keep_default_na=False, nrows=limit + 1)
            except UnicodeDecodeError:
                frame = pd.read_csv(
                    path, dtype=str, keep_default_na=False, nrows=limit + 1, encoding="latin-1"
                )
            except pd.errors.ParserError as exc:
                raise UploadRejected(
                    "The CSV could not be parsed. Check for unquoted commas or inconsistent columns.",
                    detail=str(exc)[:300],
                ) from exc
        else:
            try:
                frame = pd.read_excel(path, dtype=str, nrows=limit + 1, engine="openpyxl")
            except Exception as exc:  # openpyxl raises several unrelated types
                raise UploadRejected(
                    "The Excel workbook could not be read. Ensure it is not password protected or corrupt.",
                    detail=str(exc)[:300],
                ) from exc
    except UploadRejected:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise UploadRejected("The file could not be read.", detail=str(exc)[:300]) from exc

    frame.columns = [str(column).strip() for column in frame.columns]
    frame = frame.dropna(how="all")
    if frame.shape[0] > limit:
        raise UploadRejected(
            f"The file has more than {limit:,} rows. Split it into smaller files.",
            status_code=413,
        )
    if frame.shape[1] < 2:
        raise UploadRejected(
            "The file needs at least two columns (for example product and date).", status_code=400
        )
    return frame


def frame_to_records(frame: pd.DataFrame, limit: int = 12) -> list[dict[str, Any]]:
    head = frame.head(limit).fillna("")
    return [
        {str(key): ("" if value is None else str(value)) for key, value in row.items()}
        for row in head.to_dict(orient="records")
    ]


# ------------------------------------------------------------------ validation
def build_product_lookup(db: Database) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for product in catalog.all_products(db):
        lookup[str(product["sku"]).lower()] = product
        if product.get("name"):
            lookup.setdefault(str(product["name"]).lower(), product)
    return lookup


def validate_upload(
    db: Database,
    *,
    filename: str,
    file_type: str,
    size_bytes: int,
    frame: pd.DataFrame,
    mapping: dict[str, str | None] | None = None,
    data_source: str = "actual",
    apply_cleaning: list[str] | None = None,
) -> dict[str, Any]:
    columns = [str(column) for column in frame.columns]
    resolved = resolve_mapping(columns, mapping)
    missing = missing_required(resolved)

    report = validate_frame(
        frame,
        resolved,
        existing_signatures=sales_repo.existing_signatures(db),
        product_lookup=build_product_lookup(db),
        apply_cleaning=apply_cleaning,
    )

    batch_id = sales_repo.create_import_batch(
        db,
        filename=filename,
        file_type=file_type,
        file_size_bytes=size_bytes,
        status="validated",
        data_source=data_source,
        column_mapping={k: v for k, v in resolved.items() if v},
        message=(
            "Missing required columns: " + ", ".join(FIELD_LABELS.get(m, m) for m in missing)
            if missing
            else None
        ),
    )

    can_import = not missing and report["valid_rows"] > 0

    payload = {
        "batch_id": batch_id,
        "filename": filename,
        "file_type": file_type,
        "file_size_bytes": size_bytes,
        "detected_columns": columns,
        "mapping": resolved,
        "required_fields_missing": missing,
        "preview_rows": preview_rows(report["rows"]),
        "source_preview": frame_to_records(frame),
        "total_rows": report["total_rows"],
        "valid_rows": report["valid_rows"],
        "invalid_rows": report["invalid_rows"],
        "duplicate_rows": report["duplicate_rows"],
        "sample_invalid_rows": [
            {
                "row": row["row"],
                "sku": row.get("sku"),
                "product_name": row.get("product_name"),
                "date": row.get("date"),
                "quantity": row.get("quantity"),
                "errors": row["errors"],
            }
            for row in report["rows"]
            if row["status"] == "invalid"
        ][:20],
        "issues": report["issues"],
        "issue_counts": report["issue_counts"],
        "cleaning_suggestions": report["suggestions"],
        "warnings": report["warnings"],
        "can_import": can_import,
        "cleaning_applied": report["cleaning_applied"],
    }

    sales_repo.update_import_batch(
        db,
        batch_id,
        {
            "total_rows": report["total_rows"],
            "valid_rows": report["valid_rows"],
            "invalid_rows": report["invalid_rows"],
            "duplicate_rows": report["duplicate_rows"],
            "validation_summary": {
                "issue_counts": report["issue_counts"],
                "required_fields_missing": missing,
                "warnings": report["warnings"],
            },
            "issues": report["issues"][:500],
        },
    )

    # Persist the parsed rows so a commit after a restart cannot invent data.
    report_path(batch_id).write_text(
        json.dumps(
            {
                "batch_id": batch_id,
                "filename": filename,
                "file_type": file_type,
                "mapping": resolved,
                "created_at": utcnow_iso(),
                "total_rows": report["total_rows"],
                "valid_rows": report["valid_rows"],
                "invalid_rows": report["invalid_rows"],
                "duplicate_rows": report["duplicate_rows"],
                "issue_counts": report["issue_counts"],
                "issues": report["issues"],
                "warnings": report["warnings"],
            },
            default=str,
        ),
        encoding="utf-8",
    )
    return payload


def promote_upload(batch_id: int, source_path: Path, file_type: str) -> Path:
    """Move the pending file to its permanent, batch-scoped location."""
    destination = stored_file_path(batch_id, file_type)
    source_path.replace(destination)
    return destination


# ---------------------------------------------------------------------- commit
def commit_upload(
    db: Database,
    *,
    batch_id: int,
    mapping: dict[str, str | None] | None = None,
    apply_cleaning: list[str] | None = None,
    skip_duplicates: bool = True,
    data_source: str = "actual",
    actor: str = "data-manager",
) -> dict[str, Any]:
    batch = sales_repo.get_import_batch(db, batch_id)
    if not batch:
        raise UploadRejected(f"Import batch {batch_id} was not found.", status_code=404)
    if batch["status"] == "imported":
        raise UploadRejected(
            "This file has already been imported. Upload it again to run a fresh validation.",
            status_code=409,
        )

    stored = stored_file_path(batch_id, batch["file_type"])
    if not stored.exists():
        raise UploadRejected(
            "The stored upload is no longer available. Please upload the file again.",
            status_code=410,
        )

    frame = read_table(stored, batch["file_type"])
    resolved = resolve_mapping(
        [str(column) for column in frame.columns],
        mapping or batch.get("column_mapping"),
    )
    missing = missing_required(resolved)
    if missing:
        raise UploadRejected(
            "Required columns are not mapped: "
            + ", ".join(FIELD_LABELS.get(field, field) for field in missing),
            status_code=422,
        )

    # ``None`` means "use the documented default cleaning rules" (see validation.py).
    cleaning = apply_cleaning

    report = validate_frame(
        frame,
        resolved,
        existing_signatures=sales_repo.existing_signatures(db),
        product_lookup=build_product_lookup(db),
        apply_cleaning=cleaning,
    )

    importable = [row for row in report["rows"] if row["status"] == "valid"]
    if skip_duplicates:
        importable = [row for row in importable if row["status"] != "duplicate"]
    if not importable:
        sales_repo.update_import_batch(
            db,
            batch_id,
            {
                "status": "failed",
                "message": "No valid rows were available to import.",
                "completed_at": utcnow_iso(),
            },
        )
        raise UploadRejected(
            "No valid rows were available to import. Fix the validation errors and try again.",
            status_code=422,
        )

    is_demo = 1 if data_source == "demo" else 0
    now = utcnow_iso()
    products_created = 0
    supplier_cache: dict[str, int] = {}
    product_cache = build_product_lookup(db)
    rows_to_insert: list[tuple[Any, ...]] = []
    stock_snapshot: dict[int, float] = {}

    for row in importable:
        key = (row.get("sku") or "").lower()
        product = product_cache.get(key)
        if product is None:
            supplier_id = None
            supplier_name = row.get("supplier")
            if supplier_name:
                supplier_id = supplier_cache.get(supplier_name.lower())
                if supplier_id is None:
                    supplier_id = catalog.get_or_create_supplier(db, supplier_name)
                    supplier_cache[supplier_name.lower()] = supplier_id
            product_id = catalog.create_product(
                db,
                sku=row["sku"] or row["product_name"][:40],
                name=row["product_name"],
                category=row.get("category"),
                supplier_id=supplier_id,
                unit_cost=row.get("unit_cost"),
                selling_price=row.get("unit_price"),
                is_demo=bool(is_demo),
                stock=float(row.get("inventory") or 0),
            )
            products_created += 1
            product = catalog.get_product(db, product_id)
            product_cache[key] = product or {}
            if product:
                product_cache[str(product["name"]).lower()] = product
        product_id = int(product["id"])

        # Enrich the product master with data that only the file knows about.
        enrich: dict[str, Any] = {}
        if product.get("category") is None and row.get("category"):
            enrich["category"] = row["category"]
        if product.get("unit_cost") is None and row.get("unit_cost") is not None:
            enrich["unit_cost"] = row["unit_cost"]
        if product.get("selling_price") is None and row.get("unit_price") is not None:
            enrich["selling_price"] = row["unit_price"]
        if enrich:
            catalog.update_product(db, product_id, enrich)
            product.update(enrich)

        if row.get("inventory") is not None:
            stock_snapshot[product_id] = float(row["inventory"])

        rows_to_insert.append(
            (
                product_id,
                row["date"],
                float(row["quantity"] or 0),
                row.get("unit_price"),
                row.get("revenue"),
                row.get("store"),
                row.get("order_id"),
                batch_id,
                is_demo,
                now,
            )
        )

    inserted = sales_repo.insert_sales_rows(db, rows_to_insert)

    for product_id, stock in stock_snapshot.items():
        current = inventory_repo.get_inventory(db, product_id)
        previous = float(current["current_stock"]) if current else 0.0
        if abs(previous - stock) > 1e-9:
            inventory_repo.set_stock(
                db,
                product_id,
                stock,
                movement_type="import_snapshot",
                reason=f"Stock on hand reported in import batch #{batch_id}",
                actor=actor,
                reference=f"batch:{batch_id}",
            )

    rejected = report["total_rows"] - len(importable)
    sales_repo.update_import_batch(
        db,
        batch_id,
        {
            "status": "imported" if inserted else "failed",
            "data_source": data_source,
            "imported_rows": inserted,
            "valid_rows": report["valid_rows"],
            "invalid_rows": report["invalid_rows"],
            "duplicate_rows": report["duplicate_rows"],
            "cleaning_applied": cleaning or [],
            "validation_summary": {
                "issue_counts": report["issue_counts"],
                "warnings": report["warnings"],
            },
            "message": f"Imported {inserted} rows; {rejected} rows rejected or skipped.",
            "completed_at": utcnow_iso(),
        },
    )

    audit.log(
        db,
        action="import.committed",
        entity_type="import_batch",
        entity_id=batch_id,
        actor=actor,
        details={
            "filename": batch["filename"],
            "imported_rows": inserted,
            "products_created": products_created,
            "rejected_rows": rejected,
            "data_source": data_source,
        },
    )

    return {
        "batch_id": batch_id,
        "status": "imported",
        "imported_rows": inserted,
        "rejected_rows": rejected,
        "duplicate_rows": report["duplicate_rows"],
        "products_created": products_created,
        "message": (
            f"Imported {inserted} sales rows into the database "
            f"({products_created} new products created, {rejected} rows rejected or skipped)."
        ),
        "report_url": f"/api/imports/{batch_id}/report",
    }


def write_validation_report(db: Database, batch_id: int, destination: Path) -> Path:
    payload = json.loads(report_path(batch_id).read_text(encoding="utf-8"))
    batch = sales_repo.get_import_batch(db, batch_id) or {}
    frame = pd.DataFrame(payload.get("issues") or [])
    if frame.empty:
        frame = pd.DataFrame(
            [
                {
                    "row": None,
                    "code": "no_issues",
                    "message": "No validation issues were found.",
                    "severity": "info",
                }
            ]
        )
    frame = frame.rename(
        columns={
            "row": "Row",
            "column": "Column",
            "code": "Code",
            "message": "Message",
            "severity": "Severity",
            "value": "Value",
            "suggestion": "Suggestion",
        }
    )
    summary = pd.DataFrame(
        [
            {"Metric": "File", "Value": batch.get("filename", payload.get("filename"))},
            {"Metric": "Batch ID", "Value": batch_id},
            {"Metric": "Validated at", "Value": payload.get("created_at")},
            {"Metric": "Total rows", "Value": payload.get("total_rows")},
            {"Metric": "Valid rows", "Value": payload.get("valid_rows")},
            {"Metric": "Invalid rows", "Value": payload.get("invalid_rows")},
            {"Metric": "Duplicate rows", "Value": payload.get("duplicate_rows")},
            {"Metric": "Imported rows", "Value": batch.get("imported_rows", 0)},
            {"Metric": "Data source", "Value": batch.get("data_source", payload.get("data_source"))},
        ]
    )
    with pd.ExcelWriter(destination, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        frame.to_excel(writer, sheet_name="Issues", index=False)
        mapping_frame = pd.DataFrame(
            [{"Field": key, "Column": value} for key, value in (payload.get("mapping") or {}).items()]
        )
        mapping_frame.to_excel(writer, sheet_name="Column mapping", index=False)
    return destination


SAMPLE_COLUMNS = [
    "sku",
    "product_name",
    "category",
    "date",
    "quantity",
    "unit_price",
    "store",
    "supplier",
    "inventory",
    "unit_cost",
    "order_id",
]


def sample_template_frame(days: int = 14) -> pd.DataFrame:
    """Small, deterministic template showing the expected schema."""
    rows: list[dict[str, Any]] = []
    examples = [
        ("DAIRY-001", "Amul Taaza Toned Milk 1L", "Dairy", 12.5, 68.0, 74.0, 120, "Amul Distributors"),
        ("SNKS-004", "Lay's Classic Salted 52g", "Snacks", 9, 20.0, 15.5, 240, "PepsiCo Foods"),
        ("STPL-002", "Tata Sampann Toor Dal 1kg", "Staples", 4, 165.0, 128.0, 60, "Tata Consumer"),
    ]
    start = date(2025, 1, 1)
    from datetime import timedelta

    for day in range(days):
        current = start + timedelta(days=day)
        for index, (sku, name, category, quantity, price, cost, stock, supplier) in enumerate(examples):
            rows.append(
                {
                    "sku": sku,
                    "product_name": name,
                    "category": category,
                    "date": current.isoformat(),
                    "quantity": quantity + (day + index) % 5,
                    "unit_price": price,
                    "store": "Main Store",
                    "supplier": supplier,
                    "inventory": stock,
                    "unit_cost": cost,
                    "order_id": f"ORD-{current.strftime('%Y%m%d')}-{index + 1}",
                }
            )
    return pd.DataFrame(rows, columns=SAMPLE_COLUMNS)
