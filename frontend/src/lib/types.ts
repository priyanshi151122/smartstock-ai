/** Shared API types (mirrors backend Pydantic schemas). */

export type DataSource = "actual" | "demo";
export type RiskLevel = "stockout" | "high" | "medium" | "low" | "overstock" | "unknown";

export interface KpiCard {
  key: string;
  label: string;
  value: number | null;
  unit: "currency" | "units" | "count" | "ratio" | "days";
  formatted: string;
  change_pct?: number | null;
  comparison_label?: string | null;
  available: boolean;
  note?: string | null;
  tone?: "neutral" | "positive" | "warning" | "danger";
}

export interface KpiResponse {
  period: {
    start_date: string | null;
    end_date: string | null;
    label: string;
    previous_start?: string | null;
    previous_end?: string | null;
    active_days: number;
  };
  filters: Record<string, unknown>;
  cards: KpiCard[];
  data_source: DataSource;
  has_data: boolean;
  demo_share_pct: number | null;
  generated_at: string;
}

export interface TimePoint { period: string; revenue: number; units: number; orders: number }
export interface CategoryPoint { category: string; revenue: number; units: number; share: number }

export interface ProductSalesRow {
  product_id: number;
  sku: string;
  name: string;
  category: string | null;
  units: number;
  revenue: number;
  orders: number;
  avg_price: number | null;
  abc_class: string | null;
  share_of_revenue: number | null;
}

export interface InventoryRiskItem {
  product_id: number;
  sku: string;
  name: string;
  category: string | null;
  supplier_name: string | null;
  current_stock: number;
  avg_daily_demand: number;
  forecast_demand: number;
  horizon_days: number;
  demand_source: string;
  reorder_point: number;
  target_stock: number;
  safety_stock: number;
  coverage_days: number | null;
  risk_level: RiskLevel;
  risk_reason: string;
  stock_value: number | null;
}

export interface DashboardResponse {
  kpis: KpiResponse;
  granularity: string;
  sales_over_time: TimePoint[];
  revenue_by_category: CategoryPoint[];
  top_products: ProductSalesRow[];
  low_products: ProductSalesRow[];
  stock_vs_forecast: Array<{
    product_id: number;
    name: string;
    sku: string;
    current_stock: number;
    forecast_demand: number;
    horizon_days: number;
    reorder_point: number;
    risk_level: RiskLevel;
    demand_source: string;
  }>;
  inventory_risk: {
    counts: Record<RiskLevel, number>;
    items: InventoryRiskItem[];
    summary: { products: number; inventory_value: number | null; avg_cover_days: number | null; stockout_units_at_risk?: number };
    forecast_run_id: number | null;
    demand_source: string;
  };
  forecast_available: boolean;
  forecast_run: null | {
    id: number;
    horizon_days: number;
    model_used: string;
    created_at: string;
    data_source: string;
    summary_metrics: Record<string, unknown> | null;
  };
  onboarding: {
    steps: Array<{ key: string; label: string; complete: boolean; hint: string }>;
    completed: number;
    total: number;
  } | null;
}

export interface ValidationIssue {
  row: number | null;
  column: string | null;
  code: string;
  message: string;
  severity: "error" | "warning" | "info";
  value: string | null;
  suggestion: string | null;
}

export interface CleaningSuggestion {
  code: string;
  label: string;
  description: string;
  affected_rows: number;
  default_applied: boolean;
}

export interface ImportValidateResponse {
  batch_id: number;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  detected_columns: string[];
  mapping: Record<string, string | null>;
  required_fields_missing: string[];
  preview_rows: Array<Record<string, unknown>>;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  sample_invalid_rows: Array<Record<string, unknown>>;
  issues: ValidationIssue[];
  issue_counts: Record<string, number>;
  cleaning_suggestions: CleaningSuggestion[];
  warnings: string[];
  can_import: boolean;
}

export interface ImportBatch {
  id: number;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  status: string;
  data_source: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  imported_rows: number;
  message: string | null;
  created_at: string;
  completed_at: string | null;
  validation_summary: Record<string, unknown> | null;
}

export interface ForecastMetricRow {
  product_id: number;
  sku: string | null;
  product_name: string | null;
  category: string | null;
  model_name: string;
  is_baseline: boolean;
  is_selected: boolean;
  mae: number | null;
  rmse: number | null;
  wape: number | null;
  validation_days: number;
  train_observations: number;
  note: string | null;
}

export interface ForecastPoint {
  product_id: number;
  forecast_date: string;
  predicted_units: number;
  lower_bound: number | null;
  upper_bound: number | null;
  model_name: string;
  is_baseline: boolean;
}

export interface ForecastRunSummary {
  id: number;
  horizon_days: number;
  model_requested: string;
  model_used: string | null;
  baseline_used: string | null;
  status: string;
  data_source: string;
  products_forecasted: number;
  products_insufficient: number;
  train_start: string | null;
  train_end: string | null;
  validation_start: string | null;
  validation_end: string | null;
  summary_metrics: {
    selected?: { products: number; mean_mae: number | null; mean_rmse: number | null; wape: number | null; validation_days: number };
    all_models?: { products: number; mean_mae: number | null; mean_rmse: number | null; wape: number | null; validation_days: number };
    wape_improvement_vs_baseline_pct?: number | null;
    models_used?: string[];
    products_compared?: number;
    products_baseline_better_or_equal?: number;
  } | null;
  warnings: string[];
  notes: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface ForecastRunDetail extends ForecastRunSummary {
  metrics: ForecastMetricRow[];
  results: ForecastPoint[];
  limitations: string[];
}

export interface Recommendation {
  id: number;
  product_id: number;
  sku: string;
  product_name: string;
  category: string | null;
  supplier_name: string | null;
  status: "pending" | "approved" | "dismissed";
  risk_level: RiskLevel;
  current_stock: number;
  forecast_horizon_days: number;
  forecast_demand: number;
  avg_daily_demand: number;
  demand_std: number | null;
  safety_stock: number;
  reorder_point: number;
  target_stock: number;
  suggested_quantity: number;
  estimated_cost: number | null;
  lead_time_days: number;
  min_order_qty: number;
  pack_size: number;
  coverage_days: number | null;
  explanation: string;
  demand_source: string;
  decided_at: string | null;
  decided_by: string | null;
  decision_note: string | null;
  order_draft_ref: string | null;
  created_at: string;
}

export interface RecommendationList {
  items: Recommendation[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  counts: Record<string, number>;
  pending_cost: number;
  pending_units: number;
}

export interface PerformanceRow {
  product_id: number;
  sku: string;
  name: string;
  category: string | null;
  units: number;
  revenue: number;
  orders: number;
  avg_price: number | null;
  share_of_revenue: number | null;
  cumulative_share: number | null;
  abc_class: string | null;
  growth_pct: number | null;
  previous_revenue: number | null;
  gross_margin: number | null;
  gross_margin_pct: number | null;
  cost_data_available: boolean;
  demand_variability: number | null;
  variability_label: string | null;
  days_since_last_sale: number | null;
  slow_moving: boolean;
  current_stock: number | null;
  days_of_cover: number | null;
}

export interface PerformanceResponse {
  period: { start_date: string | null; end_date: string | null };
  compare_period: { start_date: string | null; end_date: string | null };
  items: PerformanceRow[];
  abc_summary: Array<{ abc_class: string; products: number; revenue: number; units: number }>;
  category_summary: Array<{
    category: string;
    products: number;
    units: number;
    revenue: number;
    margin: number | null;
    cost_known: number;
  }>;
  flags: {
    slow_moving: string[];
    best_sellers: string[];
    worst_sellers: string[];
    missing_cost_products: number;
    negative_growth_products: number;
  };
}

export interface InventoryRow {
  product_id: number;
  sku: string;
  name: string;
  category: string | null;
  supplier_name: string | null;
  current_stock: number;
  reorder_threshold: number;
  lead_time_days: number;
  min_order_qty: number;
  pack_size: number;
  safety_stock_days: number;
  review_period_days: number;
  target_cover_days: number | null;
  unit_cost: number | null;
  selling_price: number | null;
  stock_value: number | null;
  recent_daily_demand: number | null;
  days_of_cover: number | null;
  risk_level: RiskLevel;
  risk_reason: string | null;
  updated_at: string | null;
}

export interface InventoryListResponse {
  items: InventoryRow[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: {
    products: number;
    inventory_value: number | null;
    avg_cover_days: number | null;
    counts: Record<RiskLevel, number>;
    demand_source: string;
    forecast_run_id: number | null;
    total_skus: number;
  };
}

export interface StockMovement {
  id: number;
  product_id: number;
  product_name: string | null;
  sku: string | null;
  movement_type: string;
  quantity_delta: number;
  previous_stock: number;
  new_stock: number;
  reason: string | null;
  reference: string | null;
  actor: string;
  created_at: string;
}

export interface AppSettings {
  store_name: string;
  currency: string;
  currency_symbol: string;
  currency_locale: string;
  default_horizon_days: number;
  service_level_z: number;
  default_theme: "dark" | "light";
  demo_data_available: boolean;
  demo_rows: number;
  actual_rows: number;
  products: number;
  max_upload_mb: number;
  environment: string;
  app_version: string;
  database_dialect: string;
}

export interface MetaResponse {
  categories: string[];
  products: number;
  sales_rows: number;
  demo_rows: number;
  actual_rows: number;
  date_range: { start: string | null; end: string | null };
  latest_forecast_run: number | null;
  latest_forecast_at: string | null;
  onboarding: {
    steps: Array<{ key: string; label: string; complete: boolean; hint: string }>;
    completed: number;
    total: number;
  };
}

export interface ReportFile {
  filename: string;
  report_type: string;
  file_format: string;
  size_bytes: number;
  created_at: string;
  download_url: string;
}

export interface Product {
  id: number;
  sku: string;
  name: string;
  category: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  unit_cost: number | null;
  selling_price: number | null;
  uom: string;
  is_whole_units: boolean;
  is_active: boolean;
  is_demo: boolean;
  inventory: {
    product_id: number;
    current_stock: number;
    reorder_threshold: number;
    lead_time_days: number;
    min_order_qty: number;
    pack_size: number;
    safety_stock_days: number;
    review_period_days: number;
    target_cover_days: number | null;
    updated_at: string | null;
  } | null;
}

export interface SalesResponse {
  period: { start_date: string | null; end_date: string | null; granularity: string };
  totals: {
    revenue: number;
    units: number;
    rows: number;
    products: number;
    orders: number;
    active_days: number;
    first_date: string | null;
    last_date: string | null;
    demo_rows: number;
  };
  series: TimePoint[];
  categories: CategoryPoint[];
  products: Array<
    ProductSalesRow & { sku: string; name: string; category: string | null; orders: number; avg_price: number | null }
  >;
  product_count: number;
}

export interface ProductHistoryPoint {
  period: string;
  units: number;
  revenue: number;
}

export interface ProductHistoryResponse {
  product_id: number;
  sku: string;
  name: string;
  category: string | null;
  granularity: string;
  history: ProductHistoryPoint[];
  total_units: number;
  total_revenue: number;
}
