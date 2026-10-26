# SmartStock AI — Smart Shop Sales & Demand Forecasting System

A full-stack retail intelligence application for small shops, grocery stores and supermarkets.
It ingests a shop's own sales exports, stores them in a normalised database, calculates KPIs,
trains per-product demand forecasts with honest back-testing, and turns them into explainable
reorder recommendations.

* **Frontend** — React 18 + TypeScript + Vite + Tailwind + Recharts + Lucide, 9 pages, dark/light themes
* **Backend** — FastAPI + Pydantic v2 + Pandas/NumPy + scikit-learn (+ optional XGBoost) + SQLite
* **No mocks** — every number on screen comes from persisted rows via a real API call

| Overview (dark) | Reorder queue | Reports |
| --- | --- | --- |
| ![Overview](docs/screenshots/overview-dark.png) | ![Reorder](docs/screenshots/reorder.png) | ![Reports](docs/screenshots/reports.png) |

---

## 1. Quick start

```bash
# ---------------------------------------------------------------- backend
cd smartstock-ai/backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example ../.env                             # optional; defaults work as-is
python -m uvicorn app.main:app --reload --port 8000     # http://127.0.0.1:8000
```

```bash
# --------------------------------------------------------------- frontend
cd smartstock-ai/frontend
npm install
npm run dev                                            # http://127.0.0.1:5173
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`, so both processes together give
you the full app. Open **http://127.0.0.1:5173**.

**Single-port production mode** (FastAPI serves the built SPA):

```bash
cd smartstock-ai/frontend && npm run build             # → frontend/dist
cd ../backend && python -m uvicorn app.main:app --port 8000
# open http://127.0.0.1:8000  (UI) and http://127.0.0.1:8000/api/docs (Swagger)
```

### Load demo data (60 seconds to a full dashboard)

Either click **“Load demo data”** on an empty dashboard, or:

```bash
cd backend
python scripts/seed_demo.py --forecast       # 7,734 synthetic sales rows + a 14-day forecast + recommendations
```

The demo dataset is **synthetic and always labelled** `is_demo = 1`. Filter any page to
*Real imported records* to exclude it, or remove it from **Settings → Demo dataset**.

### Demo login

**There is no authentication in this build** — no login screen, no default credentials, and the
API is unauthenticated. Anyone who can reach the port can use it, so deploy it behind your own
gateway/reverse-proxy authentication before exposing it to a network. (Stated explicitly here
because the brief asked for demo credentials *only if authentication exists*.)

---

## 2. Walking the acceptance criteria

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | Start with documented commands | Section 1 |
| 2 | Upload valid CSV/XLSX | **Data Import** → drop `data/samples/sales_demo_12_months.csv` (or `.xlsx`) |
| 3 | Inspect validation, then import | Validation results panel → *Import N valid rows*; try `data/samples/sales_validation_test.csv` for the failure path |
| 4 | KPIs from persisted records | **Overview** cards; row counts in the sidebar footer and `GET /api/health` |
| 5 | Forecast + metrics | **Demand Forecasting** → *Run forecast* → MAE/RMSE/WAPE per model and per product |
| 6 | Inventory risk + explainable reorders | **Inventory**, **Reorder Recommendations** → open any row's *Explanation* |
| 7 | Modify stock → analytics update | **Inventory → Adjust** (e.g. +50) → Overview cover days / risk badges change; ledger entry appears |
| 8 | Filter dashboards and export | `FilterBar` on every analytics page; **Reports & Exports** → CSV/XLSX/PDF |
| 9 | Restart without data loss | Stop the server, start it again; `GET /api/health` keeps the same counts (verified, see §8) |
| 10 | Tests + production build | `pytest` (76 passing) and `npm run build` (clean); see §8 |

---

## 3. Project structure

```
smartstock-ai/
├── README.md                     ← you are here
├── .env.example                  ← backend configuration template (no secrets)
├── Makefile                      ← make install / dev / test / build / verify / demo
├── data/
│   ├── samples/
│   │   ├── sales_demo_12_months.csv      ← 7,734-row synthetic dataset (24 products, 12 months)
│   │   ├── sales_sample_template.csv     ← minimal template for the import screen
│   │   └── sales_validation_test.csv     ← deliberately broken file (dupes, negatives, bad dates)
│   ├── uploads/                  ← stored source files + validation reports (runtime)
│   └── reports/                  ← generated CSV/XLSX/PDF exports (runtime)
├── backend/
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py               ← FastAPI app, error handlers, SPA hosting
│   │   ├── config.py             ← env-driven settings (pydantic-settings)
│   │   ├── schemas.py            ← API contracts (Pydantic v2)
│   │   ├── utils.py              ← dates, numbers, sanitising
│   │   ├── db/
│   │   │   ├── database.py       ← driver-agnostic DB abstraction (SQLite ⇄ PostgreSQL)
│   │   │   ├── schema.sql        ← normalised schema
│   │   │   └── migrations/*.sql  ← additive, idempotent migrations
│   │   ├── repositories/         ← parameterised data access (sales, catalog, inventory, forecasts, audit)
│   │   ├── services/
│   │   │   ├── validation.py     ← column mapping + row-level validation/cleaning
│   │   │   ├── imports.py        ← upload safety, parsing, commit
│   │   │   ├── analytics.py      ← KPIs, ABC, performance
│   │   │   ├── forecasting.py    ← the forecasting engine
│   │   │   ├── inventory_logic.py← reorder maths, risk, recommendations
│   │   │   ├── reports.py        ← CSV/XLSX/PDF generation
│   │   │   └── demo.py           ← deterministic synthetic dataset
│   │   └── routers/              ← analytics, imports, products, inventory, forecasts,
│   │                               recommendations, reports, settings
│   ├── scripts/
│   │   ├── generate_sample_data.py
│   │   └── seed_demo.py
│   └── tests/                    ← 76 pytest tests (validation, forecasting, inventory, API)
└── frontend/
    ├── package.json, vite.config.ts, tailwind.config.js, tsconfig.json
    └── src/
        ├── main.tsx, App.tsx, index.css
        ├── context/AppContext.tsx      ← theme, filters, settings, toasts
        ├── lib/{api,types,format,hooks}.ts
        ├── components/{AppShell,ui,charts,DataTable,FilterBar,KpiGrid,Banners}.tsx
        ├── pages/  Overview · SalesAnalytics · DemandForecasting · Inventory ·
        │           ProductPerformance · ReorderRecommendations · DataImport · Reports · Settings
        └── test/   23 vitest tests (formatting, table, KPI cards, API error mapping)
```

---

## 4. Architecture

```
Browser (React SPA)
   │  Axios  /api/*
   ▼
FastAPI routers ──► services (validation · analytics · forecasting · inventory · reports)
   │                        │
   │                        ▼
   │                 repositories (parameterised SQL)
   ▼                        │
error handlers / Pydantic   ▼
                     Database abstraction ──► SQLite (dev)  |  psycopg → PostgreSQL (prod)
```

* **No ORM, no string interpolation.** Every statement uses `?` placeholders; the abstraction
  rewrites them to `%s` for PostgreSQL. The only interpolated identifiers are sort columns, which
  are validated against a fixed allow-list (`assert_identifier`, per-route regex patterns).
* **Layering.** Routers do HTTP + validation only; services hold the maths; repositories hold SQL.
  Services take a `Database` handle, which makes them directly unit-testable.
* **Settings** come from environment variables (`app/config.py`); nothing sensitive is committed.
* **Errors** are normalised to `{"error": {"status", "message", "issues?", "path", "timestamp"}}`.
  Unhandled exceptions return a 500 *without* stack traces or server paths (logged server-side).
* **Migrations.** `schema.sql` is idempotent (`CREATE TABLE IF NOT EXISTS`); afterwards every
  `db/migrations/*.sql` file is applied once and recorded in `schema_migrations`, so upgrades are
  additive and repeatable.
* **Frontend state.** One small context (theme/filters/settings/toasts) plus a `useApi` hook —
  no global store needed. Charts, tables and dialogs are shared components.

---

## 5. Data import contract

Required: **product identifier** (SKU or name), **sale date**, **quantity sold**.
Optional: unit price, revenue, category, store, supplier, inventory, unit cost, order id.

Column mapping is auto-detected from ~60 aliases (`qty`, `units sold`, `sale date`, `item`,
`stock on hand`, …) and can be overridden per field.

Validation happens **before** anything is written:

| Check | Behaviour |
|---|---|
| Unsupported extension / empty file / oversized | Rejected: `415` / `400` / `413` |
| Binary or corrupt payload (NUL bytes, non-ZIP `.xlsx`) | Rejected `400` with a repair hint |
| Missing required columns | `can_import = false`; commit returns `422` |
| Unparsable dates, non-numeric quantity, negative quantity | Row errors with **row numbers** |
| Blank quantity | Error — blank is *unknown*, never silently coerced to 0 |
| Duplicates in file / already in database | Counted, compared on (product, date, quantity, price) |
| Missing price | Warning; revenue falls back to product master or stays unavailable |
| Row limit (>200k) | Rejected `413` |

Cleaning rules are shown **before** they are applied, with the real number of affected rows
(whitespace, SKU casing, category casing, currency/number coercion, date formats, negative-value
handling, duplicate dropping, price back-fill). Nothing is discarded silently: every rejection is
counted, listed with a row number, and exportable as an XLSX validation report.

---

## 6. Forecasting methodology

Per product:

1. **Aggregate** daily units from raw sales rows.
2. **Re-index** onto a continuous calendar — a day with *no row* is a *missing observation*
   (treated as 0 or interpolated, configurable), a stored `quantity = 0` is a *genuine zero sale*.
3. **Features** (only from the past): weekday, day-of-month, month, weekend flag, `lag1`,
   `lag7`, `lag14`, rolling 7-day mean/std (shifted by 1), rolling 14-day mean.
4. **Baseline**: seasonal-naive — today = same weekday last week, applied recursively.
5. **Models**: `HistGradientBoostingRegressor`, `Ridge`, optional `XGBoost`, optional
   `RandomForest`. Multi-step forecasts are **recursive**: each prediction is appended to the
   history before the next step, so no actual future value is ever used.
6. **Validation**: rolling-origin (walk-forward) folds — up to 3 folds, each training strictly on
   data before its validation window; folds never overlap the training index (asserted by tests).
7. **Metrics**: MAE, RMSE, WAPE. WAPE is returned as `null` (not `0`) when observed demand in the
   window is zero, because it is mathematically undefined there.
8. **Model selection is honest**: the best ML model is used *only* if its WAPE beats the baseline
   on the validation window; otherwise the baseline is kept and the run notes say so.
9. **Persistence**: `forecast_runs` (params, windows, aggregate metrics, warnings, duration),
   `forecast_results` (per product/day prediction + residual-based bounds), `forecast_metrics`
   (every model, per product, marked `is_selected`).
10. **Minimum history**: 8 distinct sale days for the baseline; below `MIN_HISTORY_DAYS_FOR_ML`
    (42 by default) the model falls back to the baseline with a warning rather than pretending.
11. **Limitations** are stored with the run and rendered in the UI (promotions, stockouts,
    holiday calendar, single-window uncertainty, residual-based intervals).

### Measured evaluation results (synthetic demo dataset, 24 products, 12 months)

Produced by `POST /api/forecasts/run {"horizon_days": 14, "model": "auto"}` on
`data/samples/sales_demo_12_months.csv` (24 products, 7,734 rows, 6 categories):

| Metric (14-day horizon, 3 rolling-origin folds, 42 validation days/product) | Value |
|---|---|
| Products forecasted | 24 (0 insufficient history) |
| Selected-model mean MAE | **6.67 units/day** |
| Selected-model mean RMSE | **8.94 units/day** |
| Selected-model WAPE | **35.1 %** |
| Baseline (seasonal-naive) WAPE | 38.6 % |
| WAPE improvement vs baseline | **+10.3 %** |
| Models used | hist_gradient_boosting, ridge, xgboost (per product) |
| Run duration | ~13 s |

Interpretation: on this deliberately noisy synthetic data (product-specific noise σ≈0.12–0.34,
promo spikes, weekly + annual seasonality) the tuned models beat the weekly-naive baseline by
about 10 % in WAPE. A WAPE near 35 % means roughly one third of daily demand is unexplained — the
app reports that openly instead of claiming accuracies it cannot support. Real shop data with
stronger weekly structure typically validates better; re-run and read the numbers for your data.

---

## 7. Inventory & reorder mathematics

```
average daily demand = forecast demand over horizon ÷ days in horizon
safety stock         = max( z × σ_daily × √lead_time ,  avg_daily_demand × safety_stock_days )
reorder point        = avg daily demand × supplier lead time + safety stock
target stock         = avg daily demand × (lead time + review period) + safety stock
                       [or avg daily demand × target_cover_days + safety stock, when configured]
suggested quantity   = max(0, target stock − current stock)
                       → rounded UP to pack_size, raised to min_order_qty, whole units only
```

* `z` defaults to 1.65 (≈95 % cycle service level) and is configurable in Settings.
* Risk levels: `stockout` (0 on hand), `high` (cover < lead time, or ≤ reorder point),
  `medium` (cover < lead time + review period), `overstock` (>60 days cover, >3× target or idle
  stock with no demand), `low` otherwise.
* Every recommendation stores a written explanation quoting the exact inputs, e.g.

  > Demand source: forecast run (next 14 days) = 306.2 units, so average daily demand =
  > 306.2 / 14 = 21.87 units/day. Safety stock = 65.6 (3 days × 21.87). Reorder point =
  > 21.87 × 6d + 65.6 = 196.8. Target stock = 21.87 × (6d + 7d) + 65.6 = 349.9. Current stock 0 →
  > suggested order = max(0, 349.9 − 0) rounded to pack 6 with minimum 6 = 350 units. Risk:
  > STOCKOUT — the product is out of stock and losing sales.

* **Approving** a recommendation creates a `PO-DRAFT-#####` record plus an audit entry.
  The app never contacts a supplier and never claims an order was placed.
* When no forecast exists, recommendations fall back to **trailing 28-day demand** and say so
  (`demand_source = trailing-demand`); no forecast number is fabricated.

---

## 8. Tests, builds and verification

All commands below were run in this workspace; the results are the actual output.

```bash
cd backend && python -m pytest
# 76 passed in 8.2s

cd frontend && npx vitest run
# Test Files 3 passed (3) · Tests 23 passed (23)

cd frontend && npm run build
# tsc --noEmit (clean) + vite build → dist/  (charts 412 kB / 112 kB gzip, app 239 kB / 79 kB gzip)
```

One command runs all three plus a liveness check on the persisted database and prints a single verdict:

```bash
make verify
# -- backend tests (pytest)          → 76 passed in 7.69s
# -- frontend tests (vitest)         → 3 files / 23 tests passed
# -- production build                → tsc clean, vite built in 6.46s
# -- persisted state                 → {"status":"ok", … "products":24,"sales_records":7734}
# VERDICT: PASS
```

`make verify` exits non-zero (and prints `VERDICT: FAIL -- <step>`) the moment a step fails, so a
green verdict is only ever produced by validators that ran *after* the last change. This mirrors the
[Gravitas](https://skills.sh/udaysharmadev/Gravitas) engineering-runtime convention of pairing every
completion claim with observed output; the API check is advisory — it prints a skip notice instead of
failing when no server is listening on port 8000.

Coverage highlights (backend):

* **Import** — CSV & XLSX happy paths, invalid columns, malformed/empty/binary/oversized files,
  duplicate detection in-file and against the database, row-numbered issues, validation report.
* **KPI/analytics** — KPIs computed from persisted rows, filters changing values, ABC classes,
  missing-cost products never reported as unprofitable.
* **Forecasting** — MAE/RMSE/WAPE maths, WAPE `null` on zero demand, chronological folds,
  fold windows disjoint from training, feature-only-from-past (future mutation test), missing vs
  zero days, insufficient-history errors, persistence of runs/results/metrics.
* **Inventory** — reorder point, safety stock, target stock, MOQ/pack rounding, risk
  classification, audited adjustments, negative-stock rejection, inventory PATCH → ledger.
* **API** — product CRUD + duplicate SKU, structured 404/422/409/413/415 errors, recommendation
  approve→draft→audit, conflict on re-deciding, report generation in 3 formats, path-traversal
  rejection, and **persistence across a simulated restart** (cache cleared, DB reopened).
* **Reports** (`tests/test_reports.py`) — sales-summary and inventory-risk exports requested with an
  explicit ISO date range; this is a regression guard for a bug where report filters were forwarded
  as strings and crashed the previous-period calculation.

Frontend tests cover formatting (currency compacting, WAPE as %, em-dash fallbacks), the sortable
paginated table, KPI cards (including the “Not available” state) and API error mapping.

Manual end-to-end verification performed with a real browser (Playwright, headless Chromium)
against the production build served by FastAPI: all 9 pages rendered with **zero console errors**
at 1440×1000 and 390×844, both themes; the import screen validated the deliberately broken file
(10 rows → 4 valid / 5 invalid / 1 duplicate) and imported 4 rows; forecast run #1 completed in
~14 s. A server restart was performed and `GET /api/health` still reported `24 products /
7,734 sales records`, with forecast run #1 and its 24 recommendations intact.

The same browser pass also exercised the write paths end to end: a +40 unit stock adjustment on
*Amul Butter 500g* appeared immediately in the inventory table and in that product's movement ledger
with its reason and timestamp; a 7-day forecast was generated from the UI; a recommendation was
approved into a draft with a decision note; and a PDF sales-summary report was generated and
downloaded. The work database was then re-seeded so the shipped state is the clean demo dataset
(fresh forecast run #1, 24 pending recommendations, empty movement ledger and report folder).

---

## 9. API reference (selected)

Full interactive docs: **`/api/docs`** (Swagger UI) and **`/api/redoc`**.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Status + row counts |
| GET | `/api/meta` | Categories, date range, onboarding state |
| POST | `/api/imports/upload` | Upload + validate a CSV/XLSX (multipart) |
| POST | `/api/imports/commit` | Persist validated rows |
| GET | `/api/imports/history` · `/{id}/report` | Import history · XLSX validation report |
| POST | `/api/imports/{id}/revalidate` | Re-validate with a different mapping/cleaning set |
| GET | `/api/imports/template?format=csv\|xlsx` | Sample file download |
| GET | `/api/analytics/kpis` · `/dashboard` · `/sales` · `/performance` | Analytics |
| GET | `/api/analytics/products/{id}/history` | Per-product history |
| CRUD | `/api/products` | Product master (+ `/categories`, `/suppliers`) |
| GET/PATCH | `/api/inventory` · `/{product_id}` | Inventory list and configuration |
| POST | `/api/inventory/{id}/adjust` | Audited stock adjustment |
| GET | `/api/inventory/movements` | Movement ledger |
| GET | `/api/forecasts/models` · `/runs` · `/runs/{id}` · `/latest` | Forecast metadata & results |
| POST | `/api/forecasts/run` | Train + evaluate + persist a run |
| GET | `/api/recommendations` | Recommendation table (`sort_by`, `risk_level`, `status`, …) |
| POST | `/api/recommendations/generate` | Rebuild from the latest forecast |
| POST | `/api/recommendations/{id}/decision` | Approve (creates draft) / dismiss |
| POST | `/api/reports` · GET `/api/reports/download/{file}` | Generate & download CSV/XLSX/PDF |
| GET/PUT | `/api/settings` | Store name, currency, defaults |
| GET | `/api/audit-logs` | Audit trail |
| POST | `/api/demo/load` · `/api/demo/clear` | Synthetic dataset lifecycle |

Common query parameters on analytics endpoints: `start_date`, `end_date`, `category`,
`product_id`, `data_source=actual|demo`.

---

## 10. Security & reliability notes

* Upload type/size/row limits from settings (`MAX_UPLOAD_MB`, `MAX_UPLOAD_ROWS`); magic-byte and
  NUL-byte checks; unreadable workbooks rejected with actionable messages.
* All SQL is parameterised; sort keys use allow-lists.
* HTML/text fields are trimmed and length-capped on the way in; exports neutralise spreadsheet
  formula injection (`=`, `+`, `-`, `@` prefixed cells).
* Error responses never include stack traces, filesystem paths or SQL.
* Secrets/configuration live in `.env` (see `.env.example`); the frontend only knows `/api`.
* Audit trail records imports, stock adjustments, product changes, forecast runs, settings edits
  and every recommendation decision (including the generated draft reference).
* Destructive actions are explicit: demo removal deletes only `is_demo = 1` rows; products are
  soft-deleted (`is_active = 0`) so history stays intact.

---

## 11. Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/smartstock.db` | `sqlite:///…` or `postgresql://…` |
| `DATA_DIR` | `./data` | Uploads and generated reports |
| `MAX_UPLOAD_MB` | `10` | Upload size ceiling |
| `MAX_UPLOAD_ROWS` | `200000` | Row ceiling per file |
| `MIN_HISTORY_DAYS_FOR_ML` | `42` | Below this, the baseline is used |
| `DEFAULT_HORIZON_DAYS` | `14` | Default forecast horizon |
| `SERVICE_LEVEL_Z` | `1.65` | Safety-stock z-score |
| `CORS_ORIGINS` | localhost:5173/4173 | Additional dev origins |
| `SERVE_FRONTEND` | `true` | Serve `frontend/dist` from FastAPI |

**PostgreSQL**: set `DATABASE_URL=postgresql://user:pass@host/db`, `pip install "psycopg[binary]"`,
and restart — the schema and all queries are written to work on both engines.

---

## 12. Reproducibility

* Demo data is generated with `numpy.random.default_rng(20240517)` and a fixed product catalogue;
  the window ends yesterday so risk/cover numbers stay current, and re-running with the same
  anchor date reproduces identical numbers.
* Regenerate the shipped sample files: `python scripts/generate_sample_data.py [--seed N] [--days N]`.
* Forecasts and models are seeded (`random_state=42`); no step depends on wall-clock ordering.

---

## 13. Known limitations

* No authentication/roles (see §1) — the decision endpoints accept an `actor` string for auditing.
* Forecasts are per-product and weekly-seasonal; there is no promotion, price-elasticity or
  inter-product substitution modelling, and no external holiday calendar.
* Prediction intervals are residual-based approximations, not calibrated quantiles.
* Single-process SQLite writes (WAL enabled); use PostgreSQL for many concurrent writers.
* CSV exports contain the primary sheet only (use XLSX for all sheets); the PDF is a summary,
  not a paginated full-data dump.
