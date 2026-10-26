"""Column detection, row validation and cleaning suggestions for sales files.

Everything here is a pure function over a pandas DataFrame so it can be unit
tested without touching the database or the filesystem.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import pandas as pd

from app.utils import is_blank, safe_float, sanitize_text, to_date

#: Canonical field -> accepted header aliases (compared after normalisation).
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "sku": (
        "sku", "productid", "productcode", "itemcode", "itemid", "code",
        "productsku", "id",
    ),
    "product_name": (
        "productname", "product", "itemname", "item", "description", "name",
        "producttitle",
    ),
    "date": (
        "date", "saledate", "salesdate", "transactiondate", "orderdate", "day",
        "invoicedate", "purchasedate", "dateofsale",
    ),
    "quantity": (
        "quantity", "qty", "units", "unitssold", "quantitysold", "sold",
        "unitssales", "salesqty", "quantitysoldunits",
    ),
    "unit_price": (
        "unitprice", "price", "sellingprice", "rate", "unitrate", "mrp",
        "priceperunit",
    ),
    "revenue": (
        "revenue", "total", "totalamount", "salesamount", "amount", "linetotal",
        "grosssales", "salesvalue",
    ),
    "category": ("category", "productcategory", "categoryname", "department", "segment"),
    "store": ("store", "storename", "location", "branch", "outlet", "shop"),
    "supplier": ("supplier", "suppliername", "vendor", "vendorname"),
    "inventory": (
        "inventory", "stock", "currentstock", "stockonhand", "onhand",
        "quantityinstock", "inventorylevel", "closingstock",
    ),
    "unit_cost": ("unitcost", "cost", "costprice", "purchaseprice", "buyprice"),
    "order_id": ("orderid", "order", "invoiceid", "billid", "transactionid", "receiptid"),
}

REQUIRED_ONE_OF: tuple[tuple[str, ...], ...] = (("sku", "product_name"),)
REQUIRED_FIELDS: tuple[str, ...] = ("date", "quantity")

FIELD_LABELS: dict[str, str] = {
    "sku": "Product ID / SKU",
    "product_name": "Product name",
    "date": "Sale date",
    "quantity": "Quantity sold",
    "unit_price": "Unit price",
    "revenue": "Revenue",
    "category": "Category",
    "store": "Store",
    "supplier": "Supplier",
    "inventory": "Current inventory",
    "unit_cost": "Unit cost",
    "order_id": "Order ID",
}

#: Cleaning operations the user can opt into before importing.
CLEANING_OPS: dict[str, dict[str, str]] = {
    "trim_whitespace": {
        "label": "Trim whitespace & collapse spaces",
        "description": "Remove leading/trailing spaces and duplicate inner spaces from text fields.",
    },
    "uppercase_sku": {
        "label": "Normalise SKU casing",
        "description": "Uppercase product identifiers so 'abc-1' and 'ABC-1' are treated as the same SKU.",
    },
    "titlecase_category": {
        "label": "Normalise category casing",
        "description": "Title-case categories so 'dairy' and 'Dairy' merge into one category.",
    },
    "coerce_numeric": {
        "label": "Coerce formatted numbers",
        "description": "Strip currency symbols, thousands separators and parentheses from numeric cells.",
    },
    "parse_date_formats": {
        "label": "Accept common date formats",
        "description": "Parse DD-MM-YYYY, MM/DD/YYYY, YYYY/MM/DD and Excel serial dates.",
    },
    "exclude_negative_quantities": {
        "label": "Exclude negative quantities",
        "description": "Rows with negative quantities (returns / typos) are rejected instead of imported.",
    },
    "abs_negative_quantities": {
        "label": "Convert negative quantities to positive",
        "description": "Treat a negative quantity as a data-entry sign error and use its absolute value.",
    },
    "drop_duplicate_rows": {
        "label": "Drop duplicate rows",
        "description": "Rows repeating an existing (product, date, quantity, price) combination are not imported.",
    },
    "fill_price_from_product": {
        "label": "Fill missing price from product master",
        "description": "When unit price is blank but the product already has a price, reuse it.",
    },
    "drop_missing_identifier": {
        "label": "Reject rows without a product identifier",
        "description": "Rows with neither SKU nor product name cannot be attributed and are rejected.",
    },
}

DEFAULT_CLEANING = (
    "trim_whitespace",
    "uppercase_sku",
    "titlecase_category",
    "coerce_numeric",
    "parse_date_formats",
    "exclude_negative_quantities",
    "drop_duplicate_rows",
    "fill_price_from_product",
    "drop_missing_identifier",
)

DATE_WITH_DASH = re.compile(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$")


def normalise_header(name: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").strip().lower())


def detect_mapping(columns: list[str]) -> dict[str, str | None]:
    """Best-effort mapping of file headers to canonical fields."""
    normalised = {normalise_header(column): column for column in columns}
    mapping: dict[str, str | None] = {field: None for field in FIELD_ALIASES}
    used: set[str] = set()

    # Pass 1: exact alias matches (longest aliases first so "unitprice" wins over "price").
    for field, aliases in FIELD_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            column = normalised.get(alias)
            if column and column not in used:
                mapping[field] = column
                used.add(column)
                break

    # Pass 2: containment matches for leftovers such as "Quantity Sold (units)".
    for field, aliases in FIELD_ALIASES.items():
        if mapping[field]:
            continue
        for header, original in normalised.items():
            if original in used:
                continue
            if any(alias in header for alias in aliases if len(alias) >= 4):
                mapping[field] = original
                used.add(original)
                break
    return mapping


def resolve_mapping(columns: list[str], mapping: dict[str, str | None] | None) -> dict[str, str | None]:
    """Merge a user supplied mapping over auto-detection, ignoring unknown columns."""
    detected = detect_mapping(columns)
    if not mapping:
        return detected
    available = set(columns)
    merged = dict(detected)
    for field, column in mapping.items():
        if field not in FIELD_ALIASES:
            continue
        if column is None or column == "":
            merged[field] = None
        elif column in available:
            merged[field] = column
    return merged


def missing_required(mapping: dict[str, str | None]) -> list[str]:
    missing = [field for field in REQUIRED_FIELDS if not mapping.get(field)]
    for group in REQUIRED_ONE_OF:
        if not any(mapping.get(field) for field in group):
            missing.append("sku_or_product_name")
    return missing


def parse_date_value(value: Any) -> date | None:
    """Parse dates from CSV strings, Excel datetimes and Excel serial numbers."""
    if is_blank(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Excel serial date (1900 date system) between 1954 and 2064.
        if 20000 <= float(value) <= 60000:
            return (date(1899, 12, 30) + timedelta(days=int(value)))
        return None
    parsed = to_date(value)
    if parsed:
        return parsed
    try:
        stamp = pd.to_datetime(str(value), dayfirst=bool(DATE_WITH_DASH.match(str(value))), errors="raise")
        return stamp.date()
    except (ValueError, TypeError):
        return None


def parse_quantity(value: Any) -> tuple[float | None, str | None]:
    number = safe_float(value)
    if number is None:
        return None, "not_numeric"
    return number, None


def _issue(
    *,
    row: int | None,
    code: str,
    message: str,
    severity: str = "error",
    column: str | None = None,
    value: Any = None,
    suggestion: str | None = None,
) -> dict[str, Any]:
    return {
        "row": row,
        "column": column,
        "code": code,
        "message": message,
        "severity": severity,
        "value": None if value is None else str(value)[:80],
        "suggestion": suggestion,
    }


def validate_frame(
    df: pd.DataFrame,
    mapping: dict[str, str | None],
    *,
    existing_signatures: set[str] | None = None,
    product_lookup: dict[str, dict[str, Any]] | None = None,
    apply_cleaning: list[str] | None = None,
    max_issues: int = 500,
    today: date | None = None,
) -> dict[str, Any]:
    """Validate a raw sales frame and return structured results.

    Returns a dict with:
      ``rows`` (normalised, importable records), ``issues``, ``issue_counts``,
      ``suggestions``, ``duplicate_rows``, ``invalid_rows``, ``warnings``.
    """
    cleaning = set(DEFAULT_CLEANING if apply_cleaning is None else apply_cleaning)
    existing_signatures = existing_signatures or set()
    product_lookup = {k.lower(): v for k, v in (product_lookup or {}).items()}
    today = today or date.today()
    max_future = today + timedelta(days=2)
    min_past = date(1990, 1, 1)

    issues: list[dict[str, Any]] = []
    suggestion_counts: dict[str, int] = {}
    # Counts how often each *cleaning rule* actually changed something, so the UI
    # can show real "affected rows" numbers instead of guesses.
    op_counts: dict[str, int] = {code: 0 for code in CLEANING_OPS}
    rows: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    duplicate_rows = 0
    invalid_rows = 0
    warnings: list[str] = []

    def add_issue(**kwargs: Any) -> dict[str, Any]:
        issue = _issue(**kwargs)
        if len(issues) < max_issues:
            issues.append(issue)
        code = issue["code"] or ""
        if code:
            suggestion_counts[code] = suggestion_counts.get(code, 0) + 1
        return issue

    def cell(record: pd.Series, field: str) -> Any:
        column = mapping.get(field)
        if not column or column not in record.index:
            return None
        return record[column]

    for position, (_, record) in enumerate(df.iterrows()):
        row_number = position + 2  # +1 for header row, +1 for 1-based numbering
        row_issues: list[dict[str, Any]] = []

        def row_issue(**kwargs: Any) -> None:
            kwargs.setdefault("row", row_number)
            row_issues.append(add_issue(**kwargs))

        # ---------------------------------------------------------- identifier
        sku_raw = cell(record, "sku")
        name_raw = cell(record, "product_name")
        sku = sanitize_text(sku_raw, 64)
        name = sanitize_text(name_raw, 200)
        for raw_value, cleaned in ((sku_raw, sku), (name_raw, name)):
            if isinstance(raw_value, str) and cleaned is not None and raw_value != cleaned:
                op_counts["trim_whitespace"] += 1
        if sku and "uppercase_sku" in cleaning:
            if sku != sku.upper():
                op_counts["uppercase_sku"] += 1
            sku = sku.upper()

        category_raw = cell(record, "category")
        category = sanitize_text(category_raw, 120)
        if category and "titlecase_category" in cleaning:
            if category != category.title():
                op_counts["titlecase_category"] += 1
            category = category.title()

        if not sku and not name:
            op_counts["drop_missing_identifier"] += 1
            row_issue(
                code="missing_product_identifier",
                message="Row has neither a product ID nor a product name.",
                severity="error",
                suggestion="Provide at least one identifier, or map the correct column.",
            )
        if not sku and name:
            sku = re.sub(r"[^A-Za-z0-9]+", "-", name.upper()).strip("-")[:40] or None

        # ----------------------------------------------------------------- date
        raw_date = cell(record, "date")
        parsed_date = parse_date_value(raw_date) if "parse_date_formats" in cleaning else to_date(raw_date)
        if (
            parsed_date is not None
            and isinstance(raw_date, str)
            and raw_date.strip()[:10] != parsed_date.isoformat()
        ):
            op_counts["parse_date_formats"] += 1
        if is_blank(raw_date):
            row_issue(
                code="missing_date",
                message="Sale date is blank.",
                column=mapping.get("date"),
                suggestion="Every sales row needs a date; blank dates cannot be placed on a timeline.",
            )
        elif parsed_date is None:
            row_issue(
                code="invalid_date",
                message=f"Could not parse '{str(raw_date)[:24]}' as a date.",
                column=mapping.get("date"),
                value=raw_date,
                suggestion="Use ISO (YYYY-MM-DD) or a recognisable day-first format.",
            )
        elif parsed_date > max_future or parsed_date < min_past:
            row_issue(
                code="date_out_of_range",
                message=f"Date {parsed_date.isoformat()} is outside the accepted range (1990-01-01 to {max_future.isoformat()}).",
                column=mapping.get("date"),
                value=parsed_date.isoformat(),
            )

        # ------------------------------------------------------------- quantity
        raw_quantity = cell(record, "quantity")
        quantity_value = raw_quantity
        if "coerce_numeric" in cleaning and isinstance(raw_quantity, str):
            if raw_quantity.strip() != raw_quantity.strip().replace(",", "").replace("\u20b9", "").replace("$", ""):
                op_counts["coerce_numeric"] += 1
            quantity_value = raw_quantity.strip().replace(",", "")
        quantity, quantity_error = parse_quantity(quantity_value)
        if is_blank(raw_quantity):
            row_issue(
                code="missing_quantity",
                message="Quantity sold is blank.",
                column=mapping.get("quantity"),
                suggestion="Blank quantity means unknown, not zero. Fill it in or remove the row.",
            )
        elif quantity_error:
            row_issue(
                code="invalid_quantity",
                message=f"Quantity '{str(raw_quantity)[:24]}' is not a number.",
                column=mapping.get("quantity"),
                value=raw_quantity,
            )
        elif quantity is not None and quantity < 0:
            if "abs_negative_quantities" in cleaning:
                op_counts["abs_negative_quantities"] += 1
                quantity = abs(quantity)
                add_issue(
                    row=row_number,
                    code="negative_quantity_corrected",
                    message=f"Negative quantity {quantity_value} converted to a positive value.",
                    severity="warning",
                    column=mapping.get("quantity"),
                    suggestion="Review whether this row was a return.",
                )
            else:
                op_counts["exclude_negative_quantities"] += 1
                row_issue(
                    code="negative_quantity",
                    message=f"Quantity {quantity:g} is negative (returns are not supported by this importer).",
                    column=mapping.get("quantity"),
                    value=quantity,
                    suggestion="Exclude the row, or enable the absolute-value cleaning rule.",
                )

        # ---------------------------------------------------------------- price
        raw_price = cell(record, "unit_price")
        price_value = raw_price
        if "coerce_numeric" in cleaning and isinstance(raw_price, str):
            if raw_price.strip() != raw_price.strip().replace(",", "").replace("\u20b9", "").replace("$", ""):
                op_counts["coerce_numeric"] += 1
            price_value = raw_price.strip().replace(",", "").replace("\u20b9", "").replace("$", "")
        price = safe_float(price_value)
        if is_blank(raw_price):
            lookup = product_lookup.get((sku or "").lower()) or product_lookup.get((name or "").lower())
            fallback = lookup.get("selling_price") if lookup else None
            if fallback is not None and "fill_price_from_product" in cleaning:
                op_counts["fill_price_from_product"] += 1
                price = float(fallback)
                add_issue(
                    row=row_number,
                    code="price_filled_from_master",
                    message=f"Unit price filled with product master value {fallback:g}.",
                    severity="info",
                )
            else:
                add_issue(
                    row=row_number,
                    code="missing_price",
                    message="Unit price is blank; revenue will be unavailable for this row.",
                    severity="warning",
                    column=mapping.get("unit_price"),
                )
                suggestion_counts["missing_price"] = suggestion_counts.get("missing_price", 0)
        elif price is not None and price < 0:
            row_issue(
                code="negative_price",
                message=f"Unit price {price:g} is negative.",
                column=mapping.get("unit_price"),
                value=price,
            )
            price = None
        elif price == 0:
            add_issue(
                row=row_number,
                code="zero_price",
                message="Unit price is zero; row is imported but contributes no revenue.",
                severity="warning",
                column=mapping.get("unit_price"),
            )

        raw_revenue = cell(record, "revenue")
        revenue = safe_float(raw_revenue)
        if revenue is None and quantity is not None and price is not None:
            revenue = round(quantity * price, 2)

        # ------------------------------------------------------------- metadata
        store = sanitize_text(cell(record, "store"), 120)
        supplier = sanitize_text(cell(record, "supplier"), 160)
        order_id = sanitize_text(cell(record, "order_id"), 80)
        inventory_raw = cell(record, "inventory")
        inventory_value = safe_float(inventory_raw)
        unit_cost = safe_float(cell(record, "unit_cost"))
        if unit_cost is not None and unit_cost < 0:
            add_issue(
                row=row_number,
                code="negative_unit_cost",
                message="Unit cost is negative; it will be ignored.",
                severity="warning",
                column=mapping.get("unit_cost"),
            )
            unit_cost = None
        if is_blank(inventory_raw) is False and inventory_value is None:
            add_issue(
                row=row_number,
                code="invalid_inventory",
                message=f"Inventory value '{str(inventory_raw)[:24]}' is not numeric; ignored.",
                severity="warning",
                column=mapping.get("inventory"),
            )

        record_row = {
            "row": row_number,
            "sku": sku,
            "product_name": name or (sku or ""),
            "category": category,
            "date": parsed_date.isoformat() if parsed_date else None,
            "quantity": quantity,
            "unit_price": price,
            "revenue": revenue,
            "store": store,
            "supplier": supplier,
            "order_id": order_id,
            "inventory": inventory_value,
            "unit_cost": unit_cost,
            "errors": [i["code"] for i in row_issues if i["severity"] == "error"],
            "flags": [i["code"] for i in row_issues if i["severity"] != "error"],
        }

        # ---------------------------------------------------------- duplicates
        if not record_row["errors"]:
            lookup = product_lookup.get((sku or "").lower())
            product_id = lookup.get("id") if lookup else None
            signature = (
                f"{product_id if product_id is not None else (sku or record_row['product_name']).lower()}"
                f"|{record_row['date']}|{record_row['quantity']}"
                f"|{-1 if price is None else price}"
            )
            is_duplicate = False
            duplicate_code = None
            if signature in seen_signatures:
                is_duplicate, duplicate_code = True, "duplicate_in_file"
            elif product_id is not None and signature in existing_signatures:
                is_duplicate, duplicate_code = True, "duplicate_in_database"
            else:
                seen_signatures.add(signature)

            if is_duplicate:
                add_issue(
                    row=row_number,
                    code=duplicate_code or "duplicate_row",
                    message=(
                        "Duplicate of an earlier row in this file "
                        "(same product, date, quantity, price)."
                        if duplicate_code == "duplicate_in_file"
                        else "This sale already exists in the database."
                    ),
                    severity="warning" if "drop_duplicate_rows" in cleaning else "info",
                    suggestion="Enable 'Drop duplicate rows' to skip it.",
                )
                op_counts["drop_duplicate_rows"] += 1
                if "drop_duplicate_rows" in cleaning:
                    record_row["status"] = "duplicate"
                    duplicate_rows += 1
                    record_row["flags"].append("duplicate_dropped")
                else:
                    record_row["status"] = "valid"
                    record_row["flags"].append("duplicate_kept")
            else:
                record_row["status"] = "valid"
        else:
            record_row["status"] = "invalid"

        if record_row["status"] == "invalid":
            invalid_rows += 1
        rows.append(record_row)

    valid_rows = sum(1 for row in rows if row["status"] == "valid")

    if not rows:
        warnings.append("The file contains headers but no data rows.")
    if mapping.get("unit_price") is None and mapping.get("revenue") is None:
        warnings.append(
            "No price or revenue column was mapped, so revenue KPIs will be unavailable for imported rows."
        )
    if mapping.get("inventory") is None:
        warnings.append(
            "No inventory column was mapped. Stock levels fall back to existing inventory records."
        )

    suggestions = [
        {
            "code": code,
            "label": meta["label"],
            "description": meta["description"],
            "affected_rows": op_counts.get(code, 0),
            "default_applied": code in DEFAULT_CLEANING,
        }
        for code, meta in CLEANING_OPS.items()
    ]
    suggestions.sort(key=lambda item: (-item["affected_rows"], item["code"]))

    issue_counts: dict[str, int] = {}
    for issue in issues:
        issue_counts[issue["code"]] = issue_counts.get(issue["code"], 0) + 1

    return {
        "rows": rows,
        "issues": issues,
        "issue_counts": issue_counts,
        "suggestions": suggestions,
        "total_rows": len(rows),
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "duplicate_rows": duplicate_rows,
        "warnings": warnings,
        "cleaning_applied": sorted(cleaning),
    }


def preview_rows(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    keys = (
        "row", "sku", "product_name", "category", "date", "quantity",
        "unit_price", "revenue", "store", "status",
    )
    return [{key: row.get(key) for key in keys} for row in rows[:limit]]
