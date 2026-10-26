"""Regression tests for report generation."""


def test_sales_summary_report_uses_period_and_previous_period(client, demo_db):
    """Regression: the reports router forwards ISO date strings into compute_kpis,
    which used to crash with `unsupported operand type(s) for -: 'str' and 'str'`."""
    response = client.post(
        "/api/reports",
        json={
            "report_type": "sales_summary",
            "file_format": "csv",
            "start_date": "2025-01-01",
            "end_date": "2025-03-31",
            "data_source": "demo",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["report_type"] == "sales_summary"
    assert body["size_bytes"] > 0
    assert body["download_url"].endswith(".csv")

    download = client.get(body["download_url"])
    assert download.status_code == 200
    assert b"revenue" in download.content.lower()


def test_inventory_risk_report_with_date_filters(client, demo_db):
    response = client.post(
        "/api/reports",
        json={
            "report_type": "inventory_risk",
            "file_format": "xlsx",
            "start_date": "2025-04-01",
            "end_date": "2025-06-30",
            "data_source": "demo",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["download_url"].endswith(".xlsx")
