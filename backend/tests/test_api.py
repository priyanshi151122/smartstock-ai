"""End-to-end API tests: upload, analytics, products, forecasts, reports, errors."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import pytest

from app.config import get_settings
from app.db import Database, reset_database_cache


# ------------------------------------------------------------------- system
def test_health_and_api_index(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["sales_records"] == 0
    index = client.get("/api")
    assert index.status_code == 200
    assert "docs" in index.json()


def test_openapi_schema_is_generated(client):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for expected in ("/api/imports/upload", "/api/analytics/dashboard", "/api/forecasts/run", "/api/reports"):
        assert expected in paths


# ------------------------------------------------------------------ products
def test_product_crud_and_duplicate_sku(client):
    created = client.post(
        "/api/products",
        json={"sku": "SKU-1", "name": "First", "category": "Cat", "unit_cost": 8.5, "selling_price": 12.0},
    )
    assert created.status_code == 201
    product = created.json()
    assert product["sku"] == "SKU-1"
    assert product["inventory"] is not None

    duplicate = client.post("/api/products", json={"sku": "SKU-1", "name": "Copy"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["status"] == 409

    patched = client.patch(f"/api/products/{product['id']}", json={"name": "Renamed"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed"

    listing = client.get("/api/products", params={"search": "renamed"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    deleted = client.delete(f"/api/products/{product['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/products").json()["total"] == 0


def test_product_validation_errors_are_reported_per_field(client):
    response = client.post("/api/products", json={"sku": "", "name": "Missing sku"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["status"] == 422
    assert any(issue["field"] == "sku" for issue in error["issues"])


# ------------------------------------------------------------------- imports
def test_csv_upload_validation_and_commit(client, sample_csv: Path):
    with sample_csv.open("rb") as handle:
        upload = client.post(
            "/api/imports/upload",
            files={"file": (sample_csv.name, handle, "text/csv")},
        )
    assert upload.status_code == 200
    report = upload.json()
    assert report["total_rows"] == len(pd.read_csv(sample_csv))
    assert report["valid_rows"] == report["total_rows"]
    assert report["can_import"] is True
    assert report["mapping"]["quantity"] == "quantity"
    assert report["preview_rows"]

    commit = client.post("/api/imports/commit", json={"batch_id": report["batch_id"]})
    assert commit.status_code == 200
    body = commit.json()
    assert body["imported_rows"] == report["valid_rows"]
    assert body["status"] == "imported"

    # A second commit of the same batch must not duplicate rows.
    again = client.post("/api/imports/commit", json={"batch_id": report["batch_id"]})
    assert again.status_code == 409

    health = client.get("/api/health").json()
    assert health["sales_records"] == body["imported_rows"]

    dashboard = client.get("/api/analytics/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["kpis"]["has_data"] is True


def test_xlsx_upload_is_supported(client, tmp_path):
    frame = pd.DataFrame(
        [
            {"SKU": "X-1", "Item": "Excel Item", "Date": "2026-01-01", "Units": 5, "Price": 20},
            {"SKU": "X-1", "Item": "Excel Item", "Date": "2026-01-02", "Units": 7, "Price": 20},
        ]
    )
    path = tmp_path / "sales.xlsx"
    frame.to_excel(path, index=False)
    with path.open("rb") as handle:
        response = client.post(
            "/api/imports/upload",
            files={
                "file": (
                    "sales.xlsx",
                    handle,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["file_type"] == "xlsx"
    assert body["valid_rows"] == 2
    assert body["mapping"]["sku"] == "SKU"
    commit = client.post("/api/imports/commit", json={"batch_id": body["batch_id"]})
    assert commit.json()["imported_rows"] == 2


def test_invalid_columns_are_rejected_with_a_helpful_message(client):
    csv_bytes = b"foo,bar\n1,2\n3,4\n"
    response = client.post("/api/imports/upload", files={"file": ("bad.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    body = response.json()
    assert body["can_import"] is False
    assert "date" in body["required_fields_missing"]
    commit = client.post("/api/imports/commit", json={"batch_id": body["batch_id"]})
    assert commit.status_code == 422
    assert "Required columns are not mapped" in commit.json()["error"]["message"]


def test_malformed_and_unsafe_files_are_rejected(client):
    unsupported = client.post("/api/imports/upload", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert unsupported.status_code == 415

    empty = client.post("/api/imports/upload", files={"file": ("empty.csv", b"", "text/csv")})
    assert empty.status_code == 400

    fake_excel = client.post("/api/imports/upload", files={"file": ("fake.xlsx", b"not-a-zip", "application/zip")})
    assert fake_excel.status_code == 400

    binary_csv = client.post("/api/imports/upload", files={"file": ("bin.csv", b"a\x00b", "text/csv")})
    assert binary_csv.status_code == 400


def test_oversized_upload_is_rejected(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    payload = ("sku,date,quantity\n" + "A,2026-01-01,1\n" * 200_000).encode()
    response = client.post("/api/imports/upload", files={"file": ("big.csv", payload, "text/csv")})
    assert response.status_code == 413
    get_settings.cache_clear()


def test_broken_file_reports_row_level_problems_and_exports_a_report(client, broken_csv: Path):
    with broken_csv.open("rb") as handle:
        upload = client.post("/api/imports/upload", files={"file": (broken_csv.name, handle, "text/csv")})
    body = upload.json()
    assert body["invalid_rows"] >= 4
    assert body["issues"]
    assert all("row" in issue for issue in body["issues"])
    report = client.get(f"/api/imports/{body['batch_id']}/report")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    history = client.get("/api/imports/history").json()
    assert history[0]["id"] == body["batch_id"]


def test_template_download_bytes_are_valid_csv(client):
    response = client.get("/api/imports/template")
    assert response.status_code == 200
    frame = pd.read_csv(io.BytesIO(response.content))
    assert {"sku", "date", "quantity"} <= set(frame.columns)


# ------------------------------------------------------------------ analytics
def test_dashboard_kpis_are_computed_from_persisted_rows(client_with_demo):
    dashboard = client_with_demo.get("/api/analytics/dashboard").json()
    cards = {card["key"]: card for card in dashboard["kpis"]["cards"]}
    assert cards["total_revenue"]["value"] > 0
    assert cards["total_units"]["value"] > 0
    assert cards["product_count"]["value"] == 24
    assert dashboard["kpis"]["data_source"] == "demo"
    assert dashboard["sales_over_time"]
    assert dashboard["revenue_by_category"]
    assert dashboard["top_products"][0]["revenue"] >= dashboard["top_products"][-1]["revenue"]
    assert dashboard["onboarding"]["completed"] >= 1

    # Filtering must change the numbers, not just the labels.
    filtered = client_with_demo.get(
        "/api/analytics/dashboard", params={"category": "Dairy"}
    ).json()
    assert filtered["kpis"]["cards"][0]["value"] < cards["total_revenue"]["value"]


def test_product_performance_flags_missing_cost_data(client):
    client.post(
        "/api/products",
        json={"sku": "NC-1", "name": "No Cost Product", "category": "Testing", "selling_price": 10},
    )
    csv_bytes = b"sku,date,quantity,unit_price\nNC-1,2026-01-01,5,10\nNC-1,2026-01-02,6,10\n"
    upload = client.post("/api/imports/upload", files={"file": ("nc.csv", csv_bytes, "text/csv")}).json()
    client.post("/api/imports/commit", json={"batch_id": upload["batch_id"]})

    performance = client.get("/api/analytics/performance").json()
    item = performance["items"][0]
    assert item["cost_data_available"] is False
    assert item["gross_margin"] is None
    assert item["gross_margin_pct"] is None
    assert performance["flags"]["missing_cost_products"] == 1


# ----------------------------------------------------------------- forecasts
def test_forecast_run_endpoint_and_metrics(client, small_sales_db):
    response = client.post("/api/forecasts/run", json={"horizon_days": 7, "model": "seasonal_naive"})
    assert response.status_code == 201
    body = response.json()
    assert body["products_forecasted"] == 2
    assert body["results"] and body["metrics"]
    assert body["summary_metrics"]["selected"]["wape"] is not None
    assert body["limitations"]

    run_id = body["id"]
    detail = client.get(f"/api/forecasts/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == run_id

    latest = client.get("/api/forecasts/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == run_id

    product_id = small_sales_db["product_a"]
    if product_id:
        product = client.get(f"/api/forecasts/runs/{run_id}/products/{product_id}")
        assert product.status_code == 200
        assert product.json()["history"]


def test_forecast_without_data_is_a_clear_422(client):
    response = client.post("/api/forecasts/run", json={"horizon_days": 7})
    assert response.status_code == 422
    assert "No sales records" in response.json()["error"]["message"]


def test_recommendations_flow_creates_drafts_not_orders(client):
    product = client.post(
        "/api/products",
        json={"sku": "RC-1", "name": "Reorder Product", "unit_cost": 5, "selling_price": 9},
    ).json()
    product_id = product["id"]
    client.patch(
        f"/api/inventory/{product_id}",
        json={"current_stock": 2, "lead_time_days": 4, "min_order_qty": 6, "pack_size": 6},
    )
    rows = []
    for offset in range(40):
        rows.append(f"RC-1,2026-01-{(offset % 28) + 1:02d},{5 + offset % 4},9")
    csv_bytes = ("sku,date,quantity,unit_price\n" + "\n".join(rows) + "\n").encode()
    upload = client.post("/api/imports/upload", files={"file": ("rc.csv", csv_bytes, "text/csv")}).json()
    client.post("/api/imports/commit", json={"batch_id": upload["batch_id"]})

    forecast = client.post("/api/forecasts/run", json={"horizon_days": 7, "model": "seasonal_naive"})
    assert forecast.status_code == 201

    generated = client.post("/api/recommendations/generate", json={"horizon_days": 7})
    assert generated.status_code == 201
    assert generated.json()["created"] == 1

    listing = client.get("/api/recommendations").json()
    assert listing["total"] == 1
    reco = listing["items"][0]
    assert reco["suggested_quantity"] > 0
    assert reco["risk_level"] in {"stockout", "high"}
    assert "Reorder point" in reco["explanation"]
    assert reco["estimated_cost"] == pytest.approx(reco["suggested_quantity"] * 5)

    decision = client.post(
        f"/api/recommendations/{reco['id']}/decision",
        json={"status": "approved", "note": "Approve 6-pack", "actor": "manager"},
    )
    assert decision.status_code == 200
    decided = decision.json()
    assert decided["status"] == "approved"
    assert decided["order_draft_ref"].startswith("PO-DRAFT-")

    # Decisions are final for a draft, and the audit trail records the draft.
    repeat = client.post(f"/api/recommendations/{reco['id']}/decision", json={"status": "dismissed"})
    assert repeat.status_code == 409
    audit = client.get("/api/audit-logs").json()["items"]
    assert any(row["action"] == "purchase_order_draft.created" for row in audit)


# -------------------------------------------------------------------- reports
@pytest.mark.parametrize("file_format", ["csv", "xlsx", "pdf"])
def test_report_generation_and_download(client_with_demo, file_format):
    response = client_with_demo.post(
        "/api/reports",
        json={"report_type": "sales_summary", "file_format": file_format},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["size_bytes"] > 0
    download = client_with_demo.get(body["download_url"])
    assert download.status_code == 200
    assert len(download.content) == body["size_bytes"]
    if file_format == "pdf":
        assert download.content.startswith(b"%PDF")


def test_report_export_reflects_the_filters(client_with_demo):
    full = client_with_demo.post(
        "/api/reports", json={"report_type": "product_performance", "file_format": "csv"}
    ).json()
    filtered = client_with_demo.post(
        "/api/reports",
        json={"report_type": "product_performance", "file_format": "csv", "category": "Dairy"},
    ).json()
    full_rows = client_with_demo.get(full["download_url"]).content.decode().count("\n")
    filtered_rows = client_with_demo.get(filtered["download_url"]).content.decode().count("\n")
    assert filtered_rows < full_rows


def test_forecast_report_requires_a_run(client):
    response = client.post("/api/reports", json={"report_type": "demand_forecast", "file_format": "csv"})
    assert response.status_code == 422
    assert "forecast" in response.json()["error"]["message"].lower()


def test_report_download_rejects_path_traversal(client):
    response = client.get("/api/reports/download/..%2F..%2Fsmartstock.db")
    assert response.status_code == 404


# --------------------------------------------------------------- error shape
def test_unknown_route_and_missing_entities_return_structured_errors(client):
    unknown = client.get("/api/does-not-exist")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["status"] == 404

    missing = client.get("/api/products/424242")
    assert missing.status_code == 404
    assert "not found" in missing.json()["error"]["message"].lower()

    bad_param = client.get("/api/analytics/kpis", params={"product_id": 0})
    assert bad_param.status_code == 422
    assert bad_param.json()["error"]["issues"]


# -------------------------------------------------------------- persistence
def test_imported_data_survives_a_restart(client, sample_csv: Path):
    with sample_csv.open("rb") as handle:
        upload = client.post("/api/imports/upload", files={"file": (sample_csv.name, handle, "text/csv")}).json()
    committed = client.post("/api/imports/commit", json={"batch_id": upload["batch_id"]}).json()
    expected_rows = committed["imported_rows"]
    assert expected_rows > 0

    # Simulate a process restart: drop every cached connection/settings object and
    # open the same database file from scratch.
    settings = get_settings()
    url = settings.database_url
    reset_database_cache()
    get_settings.cache_clear()
    reopened = Database(url)
    reopened.initialise_schema()
    assert int(reopened.scalar("SELECT COUNT(*) AS c FROM sales_records", None, 0)) == expected_rows
    assert int(reopened.scalar("SELECT COUNT(*) AS c FROM import_batches", None, 0)) == 1

    health = client.get("/api/health").json()
    assert health["sales_records"] == expected_rows


def test_demo_data_is_labelled_and_can_be_removed(client_with_demo):
    settings = client_with_demo.get("/api/settings").json()
    assert settings["demo_data_available"] is True
    assert settings["demo_rows"] > 1000
    assert settings["actual_rows"] == 0

    dashboard = client_with_demo.get("/api/analytics/dashboard", params={"data_source": "actual"}).json()
    assert dashboard["kpis"]["has_data"] is False

    cleared = client_with_demo.post("/api/demo/clear").json()
    assert cleared["removed_rows"] > 0
    assert client_with_demo.get("/api/settings").json()["products"] == 0


def test_revalidate_endpoint_applies_a_new_cleaning_selection(client, broken_csv: Path):
    with broken_csv.open("rb") as handle:
        upload = client.post("/api/imports/upload", files={"file": (broken_csv.name, handle, "text/csv")}).json()
    assert upload["valid_rows"] == 4

    response = client.post(
        f"/api/imports/{upload['batch_id']}/revalidate",
        json={
            "cleaning": [
                "trim_whitespace",
                "uppercase_sku",
                "titlecase_category",
                "coerce_numeric",
                "parse_date_formats",
                "abs_negative_quantities",
                "drop_duplicate_rows",
                "drop_missing_identifier",
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    # the negative quantity becomes importable once absolute-value cleaning is enabled
    assert body["valid_rows"] == 5
    assert body["invalid_rows"] == 4
    assert body["batch_id"] != upload["batch_id"]  # a new validation batch is recorded
