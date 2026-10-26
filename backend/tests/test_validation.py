"""Unit tests for column detection and row validation (no database involved)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.services.validation import (
    DEFAULT_CLEANING,
    detect_mapping,
    missing_required,
    parse_date_value,
    resolve_mapping,
    validate_frame,
)

FRAME = pd.DataFrame(
    [
        # valid row
        {"Sku": "A-1", "Product Name": "Alpha", "Sale Date": "2026-01-05", "Qty": "4", "Price": "10.00"},
        # negative quantity
        {"Sku": "A-1", "Product Name": "Alpha", "Sale Date": "2026-01-06", "Qty": "-2", "Price": "10.00"},
        # unparsable date
        {"Sku": "A-2", "Product Name": "Beta", "Sale Date": "yesterday", "Qty": "3", "Price": "5.00"},
        # missing quantity
        {"Sku": "A-2", "Product Name": "Beta", "Sale Date": "2026-01-07", "Qty": "", "Price": "5.00"},
        # duplicate of row 1
        {"Sku": "A-1", "Product Name": "Alpha", "Sale Date": "2026-01-05", "Qty": "4", "Price": "10.00"},
    ]
)


def test_detect_mapping_handles_common_aliases():
    mapping = detect_mapping(["Sku", "Product Name", "Sale Date", "Qty", "Price", "Store Name"])
    assert mapping["sku"] == "Sku"
    assert mapping["product_name"] == "Product Name"
    assert mapping["date"] == "Sale Date"
    assert mapping["quantity"] == "Qty"
    assert mapping["unit_price"] == "Price"
    assert mapping["store"] == "Store Name"


def test_missing_required_fields_are_reported():
    mapping = resolve_mapping(["Qty"], None)
    assert "date" in missing_required(mapping)
    assert "sku_or_product_name" in missing_required(mapping)


def test_validate_frame_flags_each_problem_with_a_row_number():
    mapping = detect_mapping(list(FRAME.columns))
    result = validate_frame(FRAME, mapping, today=date(2026, 6, 1))

    assert result["total_rows"] == 5
    assert result["valid_rows"] == 1
    assert result["invalid_rows"] == 3
    assert result["duplicate_rows"] == 1

    codes = {issue["code"] for issue in result["issues"]}
    assert {"negative_quantity", "invalid_date", "missing_quantity", "duplicate_in_file"} <= codes

    rows_with_errors = {issue["row"] for issue in result["issues"] if issue["severity"] == "error"}
    assert rows_with_errors == {3, 4, 5}  # spreadsheet rows (header = row 1)


def test_absolute_value_cleaning_recovers_negative_quantities():
    mapping = detect_mapping(list(FRAME.columns))
    cleaning = [code for code in DEFAULT_CLEANING if code != "exclude_negative_quantities"]
    cleaning.append("abs_negative_quantities")
    result = validate_frame(FRAME, mapping, apply_cleaning=cleaning, today=date(2026, 6, 1))

    recovered = next(row for row in result["rows"] if row["row"] == 3)
    assert recovered["quantity"] == 2
    assert recovered["status"] == "valid"


def test_duplicates_are_kept_when_the_rule_is_disabled():
    mapping = detect_mapping(list(FRAME.columns))
    cleaning = [code for code in DEFAULT_CLEANING if code != "drop_duplicate_rows"]
    result = validate_frame(FRAME, mapping, apply_cleaning=cleaning, today=date(2026, 6, 1))
    assert result["duplicate_rows"] == 0
    assert any("duplicate_kept" in row["flags"] for row in result["rows"])


def test_database_duplicates_are_detected_via_signature():
    mapping = detect_mapping(list(FRAME.columns))
    frame = FRAME.iloc[[0]]
    signature = "1|2026-01-05|4.0|10.0"
    result = validate_frame(
        frame,
        mapping,
        existing_signatures={signature},
        product_lookup={"a-1": {"id": 1, "selling_price": 10.0}},
        today=date(2026, 6, 1),
    )
    assert result["duplicate_rows"] == 1
    assert result["issue_counts"]["duplicate_in_database"] == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-02-01", date(2026, 2, 1)),
        ("01-02-2026", date(2026, 2, 1)),
        ("02/01/2026", date(2026, 2, 1)),
        (45689, date(2025, 2, 1)),
        ("", None),
        ("not-a-date", None),
    ],
)
def test_parse_date_value_accepts_multiple_formats(raw, expected):
    assert parse_date_value(raw) == expected


def test_dates_far_in_the_future_are_rejected():
    frame = pd.DataFrame(
        [{"sku": "Z-1", "date": "2099-01-01", "quantity": "1", "unit_price": "2"}]
    )
    result = validate_frame(frame, detect_mapping(list(frame.columns)), today=date(2026, 6, 1))
    assert result["issue_counts"].get("date_out_of_range") == 1
    assert result["valid_rows"] == 0


def test_cleaning_suggestions_report_real_affected_rows():
    frame = pd.DataFrame(
        [
            {"sku": " a-1 ", "category": "dairy", "date": "03/04/2026", "quantity": "1,2", "unit_price": "\u20b910"},
            {"sku": "a-1", "category": "Dairy", "date": "2026-04-04", "quantity": 3, "unit_price": 10},
        ]
    )
    result = validate_frame(frame, detect_mapping(list(frame.columns)), today=date(2026, 6, 1))
    suggestions = {item["code"]: item["affected_rows"] for item in result["suggestions"]}
    assert suggestions["trim_whitespace"] >= 1
    assert suggestions["uppercase_sku"] >= 1
    assert suggestions["titlecase_category"] >= 1
    assert suggestions["coerce_numeric"] >= 2
    assert suggestions["parse_date_formats"] >= 1
    assert result["rows"][0]["quantity"] == 12
    assert result["rows"][0]["sku"] == "A-1"
    assert result["rows"][0]["category"] == "Dairy"


def test_zero_quantity_is_valid_but_zero_price_is_flagged():
    frame = pd.DataFrame([{"sku": "Z-9", "date": "2026-01-01", "quantity": "0", "unit_price": "0"}])
    result = validate_frame(frame, detect_mapping(list(frame.columns)), today=date(2026, 6, 1))
    assert result["valid_rows"] == 1
    assert result["issue_counts"].get("zero_price") == 1
    assert result["issue_counts"].get("missing_quantity") is None
