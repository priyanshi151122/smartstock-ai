"""Pydantic request/response schemas (API contract)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RiskLevel = Literal["stockout", "high", "medium", "low", "overstock", "unknown"]
RecommendationStatus = Literal["pending", "approved", "dismissed"]
DataSource = Literal["actual", "demo"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------- suppliers
class SupplierOut(ORMModel):
    id: int
    name: str
    contact_email: str | None = None
    phone: str | None = None
    lead_time_days: int = 7


# ---------------------------------------------------------------------- products
class ProductBase(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    supplier_id: int | None = None
    unit_cost: float | None = Field(default=None, ge=0)
    selling_price: float | None = Field(default=None, ge=0)
    uom: str = Field(default="unit", max_length=24)
    is_whole_units: bool = True
    is_active: bool = True

    @field_validator("sku", "name")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    supplier_id: int | None = None
    unit_cost: float | None = Field(default=None, ge=0)
    selling_price: float | None = Field(default=None, ge=0)
    uom: str | None = Field(default=None, max_length=24)
    is_whole_units: bool | None = None
    is_active: bool | None = None


class InventorySnapshot(ORMModel):
    product_id: int
    current_stock: float
    reorder_threshold: float
    lead_time_days: int
    min_order_qty: int
    pack_size: int
    safety_stock_days: float
    review_period_days: int
    target_cover_days: float | None = None
    updated_at: str | None = None


class ProductOut(ProductBase):
    id: int
    is_demo: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    supplier_name: str | None = None
    inventory: InventorySnapshot | None = None
    total_units: float | None = None
    total_revenue: float | None = None


class PaginatedProducts(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
    pages: int


# --------------------------------------------------------------------- inventory
class InventoryRow(BaseModel):
    product_id: int
    sku: str
    name: str
    category: str | None = None
    supplier_name: str | None = None
    current_stock: float
    reorder_threshold: float
    lead_time_days: int
    min_order_qty: int
    pack_size: int
    safety_stock_days: float
    review_period_days: int
    target_cover_days: float | None = None
    unit_cost: float | None = None
    selling_price: float | None = None
    stock_value: float | None = None
    recent_daily_demand: float | None = None
    days_of_cover: float | None = None
    risk_level: RiskLevel = "unknown"
    risk_reason: str | None = None
    updated_at: str | None = None


class InventoryListResponse(BaseModel):
    items: list[InventoryRow]
    total: int
    page: int
    page_size: int
    pages: int
    summary: dict[str, Any]


class InventoryUpdate(BaseModel):
    current_stock: float | None = Field(default=None, ge=0)
    reorder_threshold: float | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0, le=365)
    min_order_qty: int | None = Field(default=None, ge=1, le=100000)
    pack_size: int | None = Field(default=None, ge=1, le=100000)
    safety_stock_days: float | None = Field(default=None, ge=0, le=90)
    review_period_days: int | None = Field(default=None, ge=1, le=180)
    target_cover_days: float | None = Field(default=None, ge=0, le=365)


class StockAdjustment(BaseModel):
    quantity_delta: float
    reason: str = Field(min_length=3, max_length=280)
    actor: str = Field(default="store-manager", max_length=80)
    reference: str | None = Field(default=None, max_length=80)

    @field_validator("quantity_delta")
    @classmethod
    def _non_zero(cls, value: float) -> float:
        if abs(value) < 1e-9:
            raise ValueError("quantity_delta must not be zero")
        return value


class StockMovementOut(ORMModel):
    id: int
    product_id: int
    product_name: str | None = None
    sku: str | None = None
    movement_type: str
    quantity_delta: float
    previous_stock: float
    new_stock: float
    reason: str | None = None
    reference: str | None = None
    actor: str
    created_at: str


# ------------------------------------------------------------------------ sales
class SalesFilters(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    category: str | None = None
    product_id: int | None = None
    data_source: DataSource | None = None

    @model_validator(mode="after")
    def _check_range(self) -> "SalesFilters":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class TimePoint(BaseModel):
    period: str
    revenue: float
    units: float
    orders: int | None = None


class CategoryPoint(BaseModel):
    category: str
    revenue: float
    units: float
    share: float | None = None


class ProductSalesRow(BaseModel):
    product_id: int
    sku: str
    name: str
    category: str | None = None
    units: float
    revenue: float
    orders: int
    avg_price: float | None = None
    abc_class: str | None = None
    share_of_revenue: float | None = None


class KpiCard(BaseModel):
    key: str
    label: str
    value: float | None
    unit: Literal["currency", "units", "count", "ratio", "days"] = "count"
    formatted: str
    change_pct: float | None = None
    comparison_label: str | None = None
    available: bool = True
    note: str | None = None
    tone: Literal["neutral", "positive", "warning", "danger"] = "neutral"


class KpiResponse(BaseModel):
    period: dict[str, Any]
    filters: dict[str, Any]
    cards: list[KpiCard]
    data_source: DataSource
    has_data: bool
    demo_share_pct: float | None = None
    generated_at: str


class DashboardResponse(BaseModel):
    kpis: KpiResponse
    sales_over_time: list[TimePoint]
    revenue_by_category: list[CategoryPoint]
    top_products: list[ProductSalesRow]
    low_products: list[ProductSalesRow]
    stock_vs_forecast: list[dict[str, Any]]
    inventory_risk: dict[str, Any]
    forecast_available: bool
    forecast_run: dict[str, Any] | None = None
    onboarding: dict[str, Any] | None = None


# -------------------------------------------------------------------- forecasts
ModelChoice = Literal[
    "auto",
    "hist_gradient_boosting",
    "random_forest",
    "ridge",
    "xgboost",
    "seasonal_naive",
]


class ForecastRequest(BaseModel):
    horizon_days: Literal[7, 14, 30] = 14
    model: ModelChoice = "auto"
    product_ids: list[int] | None = None
    category: str | None = None
    data_source: DataSource | None = None
    missing_day_policy: Literal["zero", "interpolate"] = "zero"


class ForecastMetricRow(BaseModel):
    product_id: int
    sku: str | None = None
    product_name: str | None = None
    category: str | None = None
    model_name: str
    is_baseline: bool
    is_selected: bool
    mae: float | None = None
    rmse: float | None = None
    wape: float | None = None
    validation_days: int
    train_observations: int
    note: str | None = None


class ForecastPoint(BaseModel):
    product_id: int
    forecast_date: str
    predicted_units: float
    lower_bound: float | None = None
    upper_bound: float | None = None
    model_name: str
    is_baseline: bool


class ForecastRunSummary(BaseModel):
    id: int
    horizon_days: int
    model_requested: str
    model_used: str | None = None
    baseline_used: str | None = None
    status: str
    data_source: str
    products_forecasted: int
    products_insufficient: int
    train_start: str | None = None
    train_end: str | None = None
    validation_start: str | None = None
    validation_end: str | None = None
    summary_metrics: dict[str, Any] | None = None
    warnings: list[str] = []
    notes: str | None = None
    duration_ms: int | None = None
    created_at: str


class ForecastRunDetail(ForecastRunSummary):
    metrics: list[ForecastMetricRow] = []
    results: list[ForecastPoint] = []
    limitations: list[str] = []


class ForecastHistoryPoint(BaseModel):
    period: str
    actual: float | None = None
    forecast: float | None = None


class ProductForecastDetail(BaseModel):
    run: ForecastRunSummary
    product_id: int
    sku: str
    product_name: str
    history: list[ForecastHistoryPoint]
    forecast: list[ForecastPoint]
    metrics: list[ForecastMetricRow]


# --------------------------------------------------------------- recommendations
class RecommendationOut(BaseModel):
    id: int
    product_id: int
    sku: str
    product_name: str
    category: str | None = None
    supplier_name: str | None = None
    status: RecommendationStatus
    risk_level: RiskLevel
    current_stock: float
    forecast_horizon_days: int
    forecast_demand: float
    avg_daily_demand: float
    demand_std: float | None = None
    safety_stock: float
    reorder_point: float
    target_stock: float
    suggested_quantity: float
    estimated_cost: float | None = None
    lead_time_days: int
    min_order_qty: int
    pack_size: int
    coverage_days: float | None = None
    explanation: str
    demand_source: str
    decided_at: str | None = None
    decided_by: str | None = None
    decision_note: str | None = None
    order_draft_ref: str | None = None
    created_at: str


class RecommendationDecision(BaseModel):
    status: Literal["approved", "dismissed"]
    note: str | None = Field(default=None, max_length=400)
    actor: str = Field(default="store-manager", max_length=80)


class RecommendationGenerateRequest(BaseModel):
    run_id: int | None = None
    horizon_days: Literal[7, 14, 30] | None = None
    category: str | None = None
    service_level_z: float | None = Field(default=None, ge=0, le=4)


# ---------------------------------------------------------------------- imports
class ColumnMapping(BaseModel):
    product_id: str | None = None
    product_name: str | None = None
    sku: str | None = None
    date: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    revenue: str | None = None
    category: str | None = None
    store: str | None = None
    supplier: str | None = None
    inventory: str | None = None
    unit_cost: str | None = None
    order_id: str | None = None


class ValidationIssue(BaseModel):
    row: int | None = None
    column: str | None = None
    code: str
    message: str
    severity: Literal["error", "warning", "info"] = "error"
    value: str | None = None
    suggestion: str | None = None


class CleaningSuggestion(BaseModel):
    code: str
    label: str
    description: str
    affected_rows: int
    default_applied: bool = True


class ImportValidateResponse(BaseModel):
    batch_id: int
    filename: str
    file_type: str
    file_size_bytes: int
    detected_columns: list[str]
    mapping: dict[str, str | None]
    required_fields_missing: list[str]
    preview_rows: list[dict[str, Any]]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    sample_invalid_rows: list[dict[str, Any]]
    issues: list[ValidationIssue]
    issue_counts: dict[str, int]
    cleaning_suggestions: list[CleaningSuggestion]
    warnings: list[str]
    can_import: bool


class RevalidateRequest(BaseModel):
    mapping: dict[str, str | None] | None = None
    cleaning: list[str] | None = None


class ImportCommitRequest(BaseModel):
    batch_id: int
    mapping: dict[str, str | None] | None = None
    apply_cleaning: list[str] | None = None
    skip_duplicates: bool = True
    data_source: DataSource = "actual"


class ImportCommitResponse(BaseModel):
    batch_id: int
    status: str
    imported_rows: int
    rejected_rows: int
    duplicate_rows: int
    products_created: int
    message: str
    report_url: str


class ImportBatchOut(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    data_source: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    imported_rows: int
    message: str | None = None
    created_at: str
    completed_at: str | None = None
    validation_summary: dict[str, Any] | None = None


# ------------------------------------------------------------------ performance
class ProductPerformanceRow(BaseModel):
    product_id: int
    sku: str
    name: str
    category: str | None = None
    units: float
    revenue: float
    orders: int
    avg_price: float | None = None
    share_of_revenue: float | None = None
    cumulative_share: float | None = None
    abc_class: str | None = None
    growth_pct: float | None = None
    previous_revenue: float | None = None
    gross_margin: float | None = None
    gross_margin_pct: float | None = None
    cost_data_available: bool = False
    demand_variability: float | None = None
    variability_label: str | None = None
    days_since_last_sale: int | None = None
    slow_moving: bool = False
    current_stock: float | None = None
    days_of_cover: float | None = None


class PerformanceResponse(BaseModel):
    period: dict[str, Any]
    compare_period: dict[str, Any]
    items: list[ProductPerformanceRow]
    abc_summary: list[dict[str, Any]]
    category_summary: list[dict[str, Any]]
    flags: dict[str, Any]


# ---------------------------------------------------------------------- reports
ReportType = Literal[
    "sales_summary",
    "product_performance",
    "demand_forecast",
    "inventory_risk",
    "reorder_recommendations",
]


class ReportRequest(BaseModel):
    report_type: ReportType
    file_format: Literal["csv", "xlsx", "pdf"] = "xlsx"
    start_date: date | None = None
    end_date: date | None = None
    category: str | None = None
    product_id: int | None = None
    data_source: DataSource | None = None
    run_id: int | None = None


class ReportFile(BaseModel):
    filename: str
    report_type: str
    file_format: str
    size_bytes: int
    created_at: str
    download_url: str


# --------------------------------------------------------------------- settings
class SettingsOut(BaseModel):
    store_name: str
    currency: str
    currency_symbol: str
    currency_locale: str
    default_horizon_days: int
    service_level_z: float
    default_theme: Literal["dark", "light"]
    demo_data_available: bool
    demo_rows: int
    actual_rows: int
    products: int
    max_upload_mb: int
    environment: str
    app_version: str
    database_dialect: str


class SettingsUpdate(BaseModel):
    store_name: str | None = Field(default=None, min_length=1, max_length=120)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    currency_symbol: str | None = Field(default=None, min_length=1, max_length=4)
    currency_locale: str | None = Field(default=None, min_length=2, max_length=20)
    default_horizon_days: Literal[7, 14, 30] | None = None
    service_level_z: float | None = Field(default=None, ge=0, le=4)
    default_theme: Literal["dark", "light"] | None = None


class AuditLogOut(ORMModel):
    id: int
    created_at: str
    actor: str
    action: str
    entity_type: str
    entity_id: str | None = None
    details: dict[str, Any] | None = None


class MessageResponse(BaseModel):
    message: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    environment: str
    products: int
    sales_records: int
