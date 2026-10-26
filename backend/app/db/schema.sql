-- SmartStock AI - normalized schema (SQLite dialect, PostgreSQL compatible subset)
-- Created idempotently by app.db.database.Database.initialise_schema()

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS suppliers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    contact_email   TEXT,
    phone           TEXT,
    lead_time_days  INTEGER NOT NULL DEFAULT 7,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    category        TEXT,
    supplier_id     INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    unit_cost       REAL CHECK (unit_cost IS NULL OR unit_cost >= 0),
    selling_price   REAL CHECK (selling_price IS NULL OR selling_price >= 0),
    uom             TEXT NOT NULL DEFAULT 'unit',
    is_whole_units  INTEGER NOT NULL DEFAULT 1,
    is_demo         INTEGER NOT NULL DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_batches (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    filename            TEXT NOT NULL,
    file_type           TEXT NOT NULL,
    file_size_bytes     INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'validated',
    data_source         TEXT NOT NULL DEFAULT 'actual',
    total_rows          INTEGER NOT NULL DEFAULT 0,
    valid_rows          INTEGER NOT NULL DEFAULT 0,
    invalid_rows        INTEGER NOT NULL DEFAULT 0,
    duplicate_rows      INTEGER NOT NULL DEFAULT 0,
    imported_rows       INTEGER NOT NULL DEFAULT 0,
    column_mapping      TEXT,
    validation_summary  TEXT,
    issues              TEXT,
    cleaning_applied    TEXT,
    message             TEXT,
    created_at          TEXT NOT NULL,
    completed_at        TEXT
);

CREATE TABLE IF NOT EXISTS sales_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    sale_date       TEXT NOT NULL,
    quantity        REAL NOT NULL CHECK (quantity >= 0),
    unit_price      REAL CHECK (unit_price IS NULL OR unit_price >= 0),
    revenue         REAL,
    store           TEXT,
    order_id        TEXT,
    import_batch_id INTEGER REFERENCES import_batches(id) ON DELETE SET NULL,
    is_demo         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sales_date ON sales_records (sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_product_date ON sales_records (product_id, sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_batch ON sales_records (import_batch_id);

CREATE TABLE IF NOT EXISTS inventory (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL UNIQUE REFERENCES products(id) ON DELETE CASCADE,
    current_stock       REAL NOT NULL DEFAULT 0 CHECK (current_stock >= 0),
    reorder_threshold   REAL NOT NULL DEFAULT 0,
    lead_time_days      INTEGER NOT NULL DEFAULT 7 CHECK (lead_time_days >= 0),
    min_order_qty       INTEGER NOT NULL DEFAULT 1 CHECK (min_order_qty >= 1),
    pack_size           INTEGER NOT NULL DEFAULT 1 CHECK (pack_size >= 1),
    safety_stock_days   REAL NOT NULL DEFAULT 3,
    review_period_days  INTEGER NOT NULL DEFAULT 7,
    target_cover_days   REAL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    movement_type   TEXT NOT NULL,
    quantity_delta  REAL NOT NULL,
    previous_stock  REAL NOT NULL,
    new_stock       REAL NOT NULL,
    reason          TEXT,
    reference       TEXT,
    actor           TEXT NOT NULL DEFAULT 'system',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_movements_product ON stock_movements (product_id, created_at);

CREATE TABLE IF NOT EXISTS forecast_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    horizon_days        INTEGER NOT NULL,
    model_requested     TEXT NOT NULL DEFAULT 'auto',
    model_used          TEXT,
    baseline_used       TEXT,
    status              TEXT NOT NULL DEFAULT 'completed',
    data_source         TEXT NOT NULL DEFAULT 'actual',
    products_forecasted INTEGER NOT NULL DEFAULT 0,
    products_insufficient INTEGER NOT NULL DEFAULT 0,
    train_start         TEXT,
    train_end           TEXT,
    validation_start    TEXT,
    validation_end      TEXT,
    params              TEXT,
    summary_metrics     TEXT,
    warnings            TEXT,
    notes               TEXT,
    duration_ms         INTEGER,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    forecast_date   TEXT NOT NULL,
    predicted_units REAL NOT NULL,
    lower_bound     REAL,
    upper_bound     REAL,
    model_name      TEXT NOT NULL,
    is_baseline     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_forecast_results_run ON forecast_results (run_id, product_id);
CREATE INDEX IF NOT EXISTS idx_forecast_results_date ON forecast_results (forecast_date);

CREATE TABLE IF NOT EXISTS forecast_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    model_name      TEXT NOT NULL,
    is_baseline     INTEGER NOT NULL DEFAULT 0,
    is_selected     INTEGER NOT NULL DEFAULT 0,
    mae             REAL,
    rmse            REAL,
    wape            REAL,
    validation_days INTEGER NOT NULL DEFAULT 0,
    train_observations INTEGER NOT NULL DEFAULT 0,
    observed_days   INTEGER NOT NULL DEFAULT 0,
    missing_days    INTEGER NOT NULL DEFAULT 0,
    note            TEXT
);

CREATE INDEX IF NOT EXISTS idx_forecast_metrics_run ON forecast_metrics (run_id);

CREATE TABLE IF NOT EXISTS reorder_recommendations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    run_id              INTEGER REFERENCES forecast_runs(id) ON DELETE SET NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
    risk_level          TEXT NOT NULL DEFAULT 'unknown',
    current_stock       REAL NOT NULL,
    forecast_horizon_days INTEGER NOT NULL,
    forecast_demand     REAL NOT NULL,
    avg_daily_demand    REAL NOT NULL,
    demand_std          REAL,
    safety_stock        REAL NOT NULL,
    reorder_point       REAL NOT NULL,
    target_stock        REAL NOT NULL,
    suggested_quantity  REAL NOT NULL,
    estimated_cost      REAL,
    lead_time_days      INTEGER NOT NULL,
    min_order_qty       INTEGER NOT NULL DEFAULT 1,
    pack_size           INTEGER NOT NULL DEFAULT 1,
    coverage_days       REAL,
    explanation         TEXT NOT NULL,
    demand_source       TEXT NOT NULL DEFAULT 'forecast',
    decided_at          TEXT,
    decided_by          TEXT,
    decision_note       TEXT,
    order_draft_ref     TEXT,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reco_status ON reorder_recommendations (status, risk_level);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'system',
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT,
    details     TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs (created_at);

CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
