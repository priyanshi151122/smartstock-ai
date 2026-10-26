# API guide

Base URL: `http://127.0.0.1:8000/api` (dev) · interactive docs at `/api/docs` (Swagger),
`/api/redoc`, OpenAPI JSON at `/api/openapi.json`.

All responses are JSON. Errors use one shape:

```json
{
  "error": {
    "status": 422,
    "message": "Required columns are not mapped: Sale date",
    "issues": [{ "field": "sku", "message": "must not be blank" }],
    "path": "/api/imports/commit",
    "timestamp": "2026-10-25T11:20:00+00:00"
  }
}
```

## System

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | `{status, version, database, environment, products, sales_records}` |
| GET | `/api` | API index with links |
| GET | `/api/meta` | Categories, date range, onboarding state, latest forecast id |

## Import

```bash
# 1) upload + validate (nothing is written yet)
curl -F "file=@data/samples/sales_demo_12_months.csv" -F "data_source=actual" \
     http://127.0.0.1:8000/api/imports/upload

# 2) commit the valid rows
curl -X POST http://127.0.0.1:8000/api/imports/commit \
     -H 'Content-Type: application/json' \
     -d '{"batch_id": 1, "skip_duplicates": true, "data_source": "actual"}'

# 3) download the XLSX validation report
curl -OJ http://127.0.0.1:8000/api/imports/1/report
```

Upload response (abridged):

```json
{
  "batch_id": 4,
  "detected_columns": ["sku", "product_name", "category", "date", "quantity", "unit_price"],
  "mapping": {"sku": "sku", "date": "date", "quantity": "quantity", "unit_price": "unit_price"},
  "required_fields_missing": [],
  "total_rows": 10, "valid_rows": 4, "invalid_rows": 5, "duplicate_rows": 1,
  "issues": [{"row": 4, "code": "negative_quantity", "severity": "error",
               "message": "Quantity -3.0 is negative (returns are not supported by this importer).",
               "suggestion": "Exclude the row, or enable the absolute-value cleaning rule."}],
  "cleaning_suggestions": [{"code": "uppercase_sku", "affected_rows": 1, "default_applied": true}],
  "preview_rows": [{"row": 2, "sku": "DAIRY-001", "quantity": 12, "status": "valid"}],
  "can_import": true
}
```

Other endpoints: `POST /api/imports/{id}/revalidate` (body `{mapping?, cleaning?}`),
`GET /api/imports/history`, `GET /api/imports/{id}`, `GET /api/imports/fields`,
`GET /api/imports/template?format=csv|xlsx`.

Status codes: `400` malformed/empty, `413` too large/too many rows, `415` unsupported type,
`404` unknown batch, `409` already imported, `410` stored file gone, `422` required columns missing
or no valid rows.

## Analytics

Common parameters: `start_date`, `end_date` (ISO), `category`, `product_id`,
`data_source=actual|demo`.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/analytics/kpis` | KPI cards with `available` flags and explanatory `note`s |
| GET | `/api/analytics/dashboard` | KPIs + series + categories + top/low products + risk + onboarding |
| GET | `/api/analytics/sales?granularity=day|week|month` | Totals, series, category split, product ranking (with ABC) |
| GET | `/api/analytics/performance` | Per-product ABC, growth vs previous period, margin (cost-gated), variability, slow-moving |
| GET | `/api/analytics/products/{id}/history?granularity=…` | Daily/weekly/monthly units & revenue |

Absent data is represented explicitly: `value: null, available: false, note: "..."` — never as `0`.

## Products

`GET /api/products?search=&category=&page=&page_size=&sort_by=&sort_dir=` ·
`POST /api/products` (409 on duplicate SKU) · `GET|PATCH|DELETE /api/products/{id}` (DELETE is a
soft delete) · `GET /api/categories` · `GET /api/suppliers`.

## Inventory

| Method | Path | Notes |
|---|---|---|
| GET | `/api/inventory` | Rows + risk + summary counters |
| GET | `/api/inventory/summary` | Risk counts, stock value, average cover |
| GET | `/api/inventory/{product_id}` | Single row with risk |
| PATCH | `/api/inventory/{product_id}` | Rules and/or `current_stock` (routed through the ledger) |
| POST | `/api/inventory/{product_id}/adjust` | `{quantity_delta, reason, actor?, reference?}` — 422 if it would go negative |
| GET | `/api/inventory/movements?product_id=` | Append-only ledger |

## Forecasts

```bash
curl -X POST http://127.0.0.1:8000/api/forecasts/run \
  -H 'Content-Type: application/json' \
  -d '{"horizon_days": 14, "model": "auto", "missing_day_policy": "zero"}'
```

`model ∈ {auto, hist_gradient_boosting, xgboost, random_forest, ridge, seasonal_naive}`,
`horizon_days ∈ {7, 14, 30}`, optional `product_ids`, `category`, `data_source`.

Returns the run with `metrics[]` (every model per product, `is_selected`), `results[]`
(prediction per product/day), `summary_metrics.selected` and `.all_models`, `warnings[]` and
`limitations[]`. `422` when no product has usable history.

Also: `GET /api/forecasts/models`, `GET /api/forecasts/runs`, `GET /api/forecasts/runs/{id}`,
`GET /api/forecasts/latest`, `GET /api/forecasts/runs/{id}/products/{product_id}` (history + forecast
+ metrics for one product).

## Recommendations

```bash
curl -X POST http://127.0.0.1:8000/api/recommendations/generate -d '{}' -H 'Content-Type: application/json'
curl "http://127.0.0.1:8000/api/recommendations?status=pending&risk_level=stockout&sort_by=suggested_quantity&sort_dir=desc"
curl -X POST http://127.0.0.1:8000/api/recommendations/7/decision \
     -H 'Content-Type: application/json' \
     -d '{"status": "approved", "note": "Combine with weekly run", "actor": "store-manager"}'
```

Approving returns `order_draft_ref: "PO-DRAFT-00007"` and writes an audit entry. Re-deciding an
already-decided row returns `409`. Nothing is transmitted to a supplier.

## Reports

```bash
curl -X POST http://127.0.0.1:8000/api/reports \
  -H 'Content-Type: application/json' \
  -d '{"report_type": "sales_summary", "file_format": "pdf", "category": "Dairy"}'
# → {"filename": "...", "download_url": "/api/reports/download/..."}
curl -OJ http://127.0.0.1:8000/api/reports/download/<filename>
```

`report_type ∈ {sales_summary, product_performance, demand_forecast, inventory_risk,
reorder_recommendations}` · `file_format ∈ {csv, xlsx, pdf}`. Also `GET /api/reports` (recent files)
and `GET /api/reports/types`.

## Settings, audit and demo data

`GET|PUT /api/settings` (store name, currency, locale, default horizon, service-level z, theme) ·
`GET /api/audit-logs?entity_type=&action=&limit=&offset=` · `POST /api/demo/load?seed=` ·
`POST /api/demo/clear`.
