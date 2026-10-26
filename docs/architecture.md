# Architecture

## Layers

```
┌──────────────────────────────────────────────────────────────────────┐
│ React SPA (Vite, TypeScript)                                         │
│  pages → shared components (DataTable, charts, KpiGrid, FilterBar)   │
│  lib/api.ts (Axios) · context/AppContext (theme, filters, toasts)    │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ /api/*  (dev: Vite proxy → :8000)
┌───────────────────────────▼──────────────────────────────────────────┐
│ FastAPI                                                              │
│  routers/   HTTP surface, query validation, status codes             │
│  schemas.py Pydantic v2 request/response contracts                   │
│  main.py    error handlers, CORS, SPA hosting                        │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ plain dicts / dataclasses
┌───────────────────────────▼──────────────────────────────────────────┐
│ services/  (pure, testable business logic)                           │
│  validation.py     header detection, row validation, cleaning rules  │
│  imports.py        upload safety, parsing, commit orchestration      │
│  analytics.py      KPIs, ABC, performance, onboarding                │
│  forecasting.py    series building, features, back-testing, metrics  │
│  inventory_logic.py reorder maths, risk, recommendations             │
│  reports.py        CSV / XLSX / PDF writers                          │
│  demo.py           deterministic synthetic dataset                   │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ parameterised SQL ("?" placeholders)
┌───────────────────────────▼──────────────────────────────────────────┐
│ repositories/  sales · catalog · inventory · forecasts · audit       │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────────┐
│ db/database.py — driver-agnostic connection + transaction manager    │
│   sqlite3 (stdlib)                     psycopg (optional)            │
│   schema.sql (idempotent) + migrations/*.sql (applied once)          │
└──────────────────────────────────────────────────────────────────────┘
```

## Why this shape

* **Services never touch HTTP.** `forecasting.run_forecast(db, ...)` can be called from a test, a
  script (`scripts/seed_demo.py`) or a route without a request object. This is what makes the
  mathematics directly testable.
* **Repositories never build SQL from user input.** Filters are composed as `clause, params`
  pairs; only sort columns are interpolated and they are matched against a fixed mapping.
* **No ORM** keeps the schema readable and the dependency surface small, while the abstraction in
  `db/database.py` keeps the door open for PostgreSQL.
* **One payload per screen.** The dashboard endpoint returns KPIs, series, category mix, product
  leaders, risk table and onboarding in a single round-trip, so the UI never renders a
  half-populated page.

## Request lifecycle (import)

1. `POST /api/imports/upload` → `imports.save_upload` (extension, size, magic bytes) →
   `read_table` (pandas, row ceiling) → `validate_upload`.
2. `validation.validate_frame` produces normalised rows, row-numbered issues, duplicate counts and
   cleaning suggestions with real affected-row counts.
3. The parsed file is promoted to `data/uploads/batch_<id>.<ext>` and a JSON validation report is
   written next to it, so a commit after a restart cannot invent data.
4. `POST /api/imports/commit` re-reads the **stored file**, re-validates with the chosen cleaning
   set, creates missing products/suppliers, inserts sales rows in one statement batch, writes stock
   snapshots through the audited ledger, updates the batch, and writes an audit log entry.
5. Re-committing the same batch returns `409`.

## Data model

`suppliers` ← `products` → `inventory` (1:1) → `stock_movements`
`sales_records` (N:1 products, N:1 import_batches)
`forecast_runs` → `forecast_results`, `forecast_metrics`
`reorder_recommendations` (N:1 products, N:1 forecast_runs)
`audit_logs`, `app_settings`, `schema_migrations`

Notes:
* `products.is_demo` and `sales_records.is_demo` make synthetic provenance a first-class column, so
  every query can filter `data_source=actual`.
* `sales_records.revenue` is stored (quantity × price at import time) so historical revenue does not
  drift when a price changes later.
* Products are soft-deleted (`is_active = 0`) to keep historical aggregates stable.

## Frontend patterns

* `useApi(fetcher, deps)` — loading/error/data with an explicit `reload()`; keeps previous data
  while refreshing so filter changes do not flash the layout.
* Filter state lives in `AppContext` and is persisted to `localStorage`, so navigating between
  pages keeps the same date range, category and data source.
* All charts use Recharts with theme-aware colours; each chart has a `role="img"` label, tables have
  captions, dialogs trap focus and restore body scroll, and every interactive element is keyboard
  reachable (`Enter`/`Space` on rows, `Esc` to close dialogs).

## Failure modes handled explicitly

| Situation | User-visible behaviour |
|---|---|
| Backend down | Toast + inline error: “Cannot reach the SmartStock API. Is the backend running on port 8000?” |
| No data for filters | Empty state with import/demo actions, KPI cards say “Not available” |
| Missing cost data | “no cost data” instead of a margin of 0 |
| No order column | AOV card explains it needs multi-line orders |
| No forecast yet | Forecasted demand KPI explains it needs a run; risk uses trailing demand and says so |
| Too little history | Forecast API returns `422` with the day counts; run falls back to baseline with warnings |
| Unsupported upload | `415`/`400`/`413` with the specific rule that failed |
