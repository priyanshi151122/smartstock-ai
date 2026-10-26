/** Demand forecasting: run models, inspect evaluation metrics and per-product output. */

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  History,
  Info,
  Play,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { endpoints, toApiError } from "../lib/api";
import { useApi } from "../lib/hooks";
import { formatDateTime, formatNumber, formatPercent, formatRatioAsPercent } from "../lib/format";
import { ForecastChart } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { ErrorBanner } from "../components/Banners";
import {
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  Field,
  LoadingBlock,
  Modal,
  Select,
  StatPill,
  cx,
} from "../components/ui";
import type { ForecastMetricRow, ForecastRunDetail, ForecastRunSummary } from "../lib/types";

const HORIZONS = [7, 14, 30];
const MODEL_OPTIONS = [
  { value: "auto", label: "Auto — compare models, keep the best" },
  { value: "hist_gradient_boosting", label: "Gradient boosting (scikit-learn)" },
  { value: "xgboost", label: "XGBoost (if installed)" },
  { value: "random_forest", label: "Random forest" },
  { value: "ridge", label: "Ridge regression" },
  { value: "seasonal_naive", label: "Seasonal-naive baseline only" },
];

export default function DemandForecasting() {
  const { filters, settings, pushToast, refreshMeta } = useApp();
  const [horizon, setHorizon] = useState<number>(settings?.default_horizon_days ?? 14);
  const [model, setModel] = useState("auto");
  const [policy, setPolicy] = useState<"zero" | "interpolate">("zero");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [selectedProduct, setSelectedProduct] = useState<number | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const modelsApi = useApi(() => endpoints.forecastModels(), []);
  const runsApi = useApi(() => endpoints.forecastRuns({ limit: 15 }), []);
  const latestApi = useApi(
    () => endpoints.latestForecast().catch(() => null),
    [],
  );

  useEffect(() => {
    if (selectedRunId === null && latestApi.data?.id) setSelectedRunId(latestApi.data.id);
  }, [latestApi.data, selectedRunId]);

  const runApi = useApi<ForecastRunDetail | null>(
    () => (selectedRunId ? endpoints.forecastRun(selectedRunId) : Promise.resolve(null)),
    [selectedRunId],
    { enabled: selectedRunId !== null },
  );

  const run = runApi.data;
  const products = useMemo(() => {
    const map = new Map<number, { id: number; name: string; sku: string }>();
    (run?.metrics ?? []).forEach((row) => {
      if (row.product_id && !map.has(row.product_id)) {
        map.set(row.product_id, { id: row.product_id, name: row.product_name ?? `Product ${row.product_id}`, sku: row.sku ?? "" });
      }
    });
    return [...map.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [run]);

  useEffect(() => {
    if (products.length && selectedProduct === null) setSelectedProduct(products[0].id);
  }, [products, selectedProduct]);

  const productApi = useApi(
    () => (selectedRunId && selectedProduct ? endpoints.productForecast(selectedRunId, selectedProduct) : Promise.resolve(null)),
    [selectedRunId, selectedProduct],
    { enabled: Boolean(selectedRunId && selectedProduct) },
  );

  const startRun = async () => {
    setRunning(true);
    setRunError(null);
    try {
      const result = await endpoints.runForecast({
        horizon_days: horizon,
        model,
        category: filters.category,
        data_source: filters.data_source,
      });
      setSelectedRunId(result.id);
      setSelectedProduct(null);
      runsApi.reload();
      latestApi.reload();
      refreshMeta();
      pushToast({
        tone: "success",
        title: `Forecast #${result.id} completed`,
        description: `${result.products_forecasted} products · ${formatDateTime(result.created_at)}`,
      });
    } catch (error) {
      const apiError = toApiError(error);
      setRunError(apiError.message);
      pushToast({ tone: "error", title: "Forecast failed", description: apiError.message });
    } finally {
      setRunning(false);
    }
  };

  const aggregate = useMemo(() => {
    if (!run) return [];
    const totals = new Map<string, { period: string; forecast: number; lower: number; upper: number }>();
    run.results.forEach((row) => {
      const current = totals.get(row.forecast_date) ?? { period: row.forecast_date, forecast: 0, lower: 0, upper: 0 };
      current.forecast += row.predicted_units;
      current.lower += row.lower_bound ?? row.predicted_units;
      current.upper += row.upper_bound ?? row.predicted_units;
      totals.set(row.forecast_date, current);
    });
    return [...totals.values()].sort((a, b) => a.period.localeCompare(b.period));
  }, [run]);

  const metricRows = useMemo(() => run?.metrics ?? [], [run]);
  const summary = run?.summary_metrics;
  const baselineWape = summary?.selected?.wape;
  const improvement = summary?.wape_improvement_vs_baseline_pct;

  const historyColumns = useMemo(
    () => [
      {
        key: "name",
        header: "Product",
        value: (row: ForecastMetricRow) => row.product_name ?? "",
        render: (row: ForecastMetricRow) => (
          <div className="min-w-0">
            <p className="truncate font-medium">{row.product_name}</p>
            <p className="text-[10.5px] text-muted">
              {row.sku} · {row.category ?? "—"}
            </p>
          </div>
        ),
        sortable: true,
      },
      {
        key: "model",
        header: "Model",
        value: (row: ForecastMetricRow) => row.model_name,
        render: (row: ForecastMetricRow) => (
          <span className="inline-flex items-center gap-1.5">
            <span className={cx("text-[11px]", row.is_selected ? "text-ink" : "text-muted")}>{row.model_name}</span>
            {row.is_baseline ? <Badge tone="neutral">baseline</Badge> : null}
            {row.is_selected ? <Badge tone="positive">selected</Badge> : null}
          </span>
        ),
      },
      {
        key: "mae",
        header: "MAE",
        align: "right" as const,
        value: (row: ForecastMetricRow) => row.mae ?? Number.POSITIVE_INFINITY,
        render: (row: ForecastMetricRow) => (row.mae === null ? "—" : formatNumber(row.mae, 2)),
        sortable: true,
      },
      {
        key: "rmse",
        header: "RMSE",
        align: "right" as const,
        value: (row: ForecastMetricRow) => row.rmse ?? Number.POSITIVE_INFINITY,
        render: (row: ForecastMetricRow) => (row.rmse === null ? "—" : formatNumber(row.rmse, 2)),
        sortable: true,
      },
      {
        key: "wape",
        header: "WAPE",
        align: "right" as const,
        value: (row: ForecastMetricRow) => row.wape ?? Number.POSITIVE_INFINITY,
        render: (row: ForecastMetricRow) =>
          row.wape === null ? <span title="Undefined: zero demand in validation window">n/a</span> : formatRatioAsPercent(row.wape),
        sortable: true,
      },
      {
        key: "validation_days",
        header: "Val. days",
        align: "right" as const,
        hideBelow: "md" as const,
        value: (row: ForecastMetricRow) => row.validation_days,
        render: (row: ForecastMetricRow) => formatNumber(row.validation_days),
        sortable: true,
      },
    ],
    [],
  );

  const runColumns = useMemo(
    () => [
      {
        key: "id",
        header: "Run",
        value: (row: ForecastRunSummary) => row.id,
        render: (row: ForecastRunSummary) => (
          <button
            type="button"
            onClick={() => {
              setSelectedRunId(row.id);
              setSelectedProduct(null);
            }}
            className={cx("font-medium underline decoration-dotted", row.id === selectedRunId ? "text-accent" : "text-ink")}
          >
            #{row.id}
          </button>
        ),
        sortable: true,
      },
      {
        key: "horizon",
        header: "Horizon",
        align: "right" as const,
        value: (row: ForecastRunSummary) => row.horizon_days,
        render: (row: ForecastRunSummary) => `${row.horizon_days}d`,
        sortable: true,
      },
      {
        key: "model",
        header: "Models",
        hideBelow: "md" as const,
        value: (row: ForecastRunSummary) => row.model_used ?? "",
        render: (row: ForecastRunSummary) => <span className="text-[11px] text-muted">{row.model_used ?? "—"}</span>,
      },
      {
        key: "wape",
        header: "WAPE",
        align: "right" as const,
        value: (row: ForecastRunSummary) => row.summary_metrics?.selected?.wape ?? Number.POSITIVE_INFINITY,
        render: (row: ForecastRunSummary) =>
          row.summary_metrics?.selected?.wape != null ? formatRatioAsPercent(row.summary_metrics.selected.wape) : "—",
        sortable: true,
      },
      {
        key: "created",
        header: "Created",
        align: "right" as const,
        hideBelow: "sm" as const,
        value: (row: ForecastRunSummary) => row.created_at,
        render: (row: ForecastRunSummary) => <span className="text-[11px] text-muted">{formatDateTime(row.created_at)}</span>,
        sortable: true,
      },
    ],
    [selectedRunId],
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Generate a demand forecast"
          description="Chronological back-testing only: the model never sees future observations when predicting the past."
          icon={<BrainCircuit size={15} aria-hidden />}
          actions={
            <Button onClick={startRun} loading={running} icon={<Play size={13} aria-hidden />}>
              {running ? "Training & evaluating…" : "Run forecast"}
            </Button>
          }
        />
        <div className="card-pad grid grid-cols-1 gap-3 md:grid-cols-3">
          <Field label="Forecast horizon" hint="Controls the reorder horizon too.">
            <div className="flex gap-1.5" role="group" aria-label="Forecast horizon">
              {HORIZONS.map((days) => (
                <button
                  key={days}
                  type="button"
                  onClick={() => setHorizon(days)}
                  aria-pressed={horizon === days}
                  className={cx(
                    "flex-1 rounded-lg border px-2 py-1.5 text-xs transition",
                    horizon === days ? "border-accent bg-accent/10 font-medium text-accent" : "border-line text-muted hover:text-ink",
                  )}
                >
                  {days} days
                </button>
              ))}
            </div>
          </Field>
          <Field label="Model" htmlFor="forecast-model" hint={
            modelsApi.data?.available?.length
              ? `Available in this install: ${(modelsApi.data.available as string[]).join(", ")}`
              : undefined
          }>
            <Select id="forecast-model" value={model} onChange={(event) => setModel(event.target.value)}>
              {MODEL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Missing calendar days"
            htmlFor="forecast-policy"
            hint="A day with no record is different from a recorded zero sale."
          >
            <Select id="forecast-policy" value={policy} onChange={(event) => setPolicy(event.target.value as "zero" | "interpolate")}>
              <option value="zero">Treat as zero demand</option>
              <option value="interpolate">Interpolate between observations</option>
            </Select>
          </Field>
        </div>
        <div className="border-t border-line px-4 py-2.5 text-[11px] text-muted sm:px-5">
          Scope: {filters.category ?? "all categories"}
          {filters.data_source ? ` · ${filters.data_source === "demo" ? "demo data only" : "real records only"}` : " · all persisted records"} · runs
          train one model per product and typically take 10–25 seconds for a 24-product catalogue.
        </div>
        {runError ? (
          <div className="border-t border-line px-4 py-2.5 sm:px-5">
            <Callout tone="warning" title="Forecast could not run">
              {runError}
            </Callout>
          </div>
        ) : null}
      </Card>

      {running ? (
        <Card>
          <LoadingBlock label="Training models and evaluating on rolling-origin splits" rows={6} />
        </Card>
      ) : null}

      {!run && !runApi.loading && !running ? (
        <Card>
          <EmptyState
            title="No forecast run yet"
            description="Run a forecast to compare a seasonal-naive baseline against gradient-boosted models and store the evaluation metrics."
            icon={<TrendingUp size={18} aria-hidden />}
          />
        </Card>
      ) : null}

      {runError && !run ? <ErrorBanner error={{ message: runError, status: 422 }} /> : null}

      {run ? (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <StatPill label="Run" value={`#${run.id}`} />
            <StatPill label="Horizon" value={`${run.horizon_days} days`} />
            <StatPill label="Products" value={formatNumber(run.products_forecasted)} />
            <StatPill label="MAE (avg)" value={summary?.selected?.mean_mae != null ? formatNumber(summary.selected.mean_mae, 2) : "—"} />
            <StatPill label="RMSE (avg)" value={summary?.selected?.mean_rmse != null ? formatNumber(summary.selected.mean_rmse, 2) : "—"} />
            <StatPill
              label="WAPE"
              value={baselineWape != null ? formatRatioAsPercent(baselineWape) : "—"}
              tone={baselineWape == null ? "neutral" : baselineWape < 0.25 ? "good" : baselineWape < 0.45 ? "warn" : "bad"}
            />
          </div>

          <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader
                title="Aggregated forecast"
                description={`Total predicted units per day across ${run.products_forecasted} products`}
                icon={<CalendarClock size={15} aria-hidden />}
                actions={
                  <Button size="sm" variant="ghost" onClick={() => setDetailsOpen(true)} icon={<Info size={13} aria-hidden />}>
                    Run details
                  </Button>
                }
              />
              <div className="card-pad">
                <p className="mb-1 text-[10.5px] text-muted">
                  Aggregated forecast only — no actuals are plotted here because the horizon is in the future. Open a product below
                  to see history against forecast.
                </p>
                <ForecastChart
                  data={aggregate.map((row) => ({
                    period: row.period,
                    actual: null,
                    forecast: Math.round(row.forecast),
                    lower: Math.round(row.lower),
                    upper: Math.round(row.upper),
                  }))}
                  height={280}
                />
              </div>
            </Card>

            <div className="space-y-3">
              <Card className="card-pad">
                <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
                  <ShieldCheck size={14} className="text-positive" aria-hidden /> Evaluation
                </h3>
                <dl className="space-y-1.5 text-[11.5px]">
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted">Model(s) used</dt>
                    <dd className="text-right font-medium">{run.model_used ?? "—"}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted">Baseline</dt>
                    <dd className="font-medium">{run.baseline_used ?? "seasonal_naive"}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted">Training window</dt>
                    <dd className="font-medium">
                      {run.train_start ?? "—"} → {run.train_end ?? "—"}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted">Validation window</dt>
                    <dd className="font-medium">
                      {run.validation_start ?? "—"} → {run.validation_end ?? "—"}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted">WAPE improvement vs baseline</dt>
                    <dd
                      className={cx(
                        "font-medium",
                        improvement == null ? "text-muted" : improvement > 0 ? "text-positive" : "text-warning",
                      )}
                    >
                      {improvement == null ? "—" : formatPercent(improvement)}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted">Baseline better/equal for</dt>
                    <dd className="font-medium">{summary?.products_baseline_better_or_equal ?? 0} products</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted">Duration</dt>
                    <dd className="font-medium">{run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : "—"}</dd>
                  </div>
                </dl>
              </Card>

              {run.warnings.length ? (
                <Callout tone="warning" title="Model warnings">
                  <ul className="list-disc space-y-0.5 pl-3">
                    {run.warnings.slice(0, 4).map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </Callout>
              ) : (
                <Callout tone="success" title="All products had enough history">
                  Every product in scope produced a validated forecast.
                </Callout>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader
                title="Product-level history and forecast"
                description="Actual daily units for the last 90 days plus the forecast horizon"
                actions={
                  <Select
                    aria-label="Choose product"
                    className="w-56 text-xs"
                    value={selectedProduct ?? ""}
                    onChange={(event) => setSelectedProduct(Number(event.target.value))}
                  >
                    {products.map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.name}
                      </option>
                    ))}
                  </Select>
                }
              />
              {productApi.loading ? (
                <LoadingBlock rows={5} />
              ) : productApi.data ? (
                <div className="card-pad space-y-2">
                  <ForecastChart
                    data={(productApi.data.history as Array<{ period: string; actual: number | null; forecast: number | null }>).map(
                      (point) => ({ ...point, lower: null, upper: null }),
                    )}
                    height={260}
                  />
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {(productApi.data.metrics as ForecastMetricRow[]).slice(0, 4).map((metric) => (
                      <StatPill
                        key={`${metric.model_name}-${metric.is_baseline}`}
                        label={`${metric.model_name}${metric.is_selected ? " ✓" : ""}`}
                        value={metric.wape != null ? formatRatioAsPercent(metric.wape) : metric.mae != null ? formatNumber(metric.mae, 2) : "—"}
                      />
                    ))}
                  </div>
                </div>
              ) : (
                <EmptyState title="Select a product" description="Choose a product to inspect its history and forecast." />
              )}
            </Card>

            <Card>
              <CardHeader title="Model limitations" description="Read before acting on a forecast" icon={<AlertTriangle size={14} aria-hidden />} />
              <ul className="card-pad space-y-1.5 text-[11px] text-muted">
                {(run.limitations.length
                  ? run.limitations
                  : [
                      "Forecasts extrapolate recent patterns; promotions and holidays are not explicitly modelled.",
                      "Historical stockouts depress recorded demand and can cause under-forecasting.",
                    ]
                ).map((limitation) => (
                  <li key={limitation} className="flex gap-1.5">
                    <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-muted" aria-hidden />
                    {limitation}
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Per-product evaluation"
              description="Baseline and every trained model with its own validation metrics"
              actions={<Badge tone="neutral">{metricRows.length} metric rows</Badge>}
            />
            <DataTable
              rows={metricRows}
              columns={historyColumns}
              rowKey={(row) => `${row.product_id}-${row.model_name}-${row.is_baseline}`}
              pageSize={12}
              initialSort={{ key: "name", dir: "asc" }}
              emptyTitle="No metrics stored"
              caption="Per product forecast metrics"
            />
          </Card>
        </>
      ) : null}

      <Card>
        <CardHeader
          title="Run history"
          description="Every run keeps its own parameters, metrics and predictions"
          icon={<History size={15} aria-hidden />}
        />
        <DataTable
          rows={runsApi.data ?? []}
          columns={runColumns}
          rowKey={(row) => row.id}
          pageSize={6}
          initialSort={{ key: "id", dir: "desc" }}
          emptyTitle="No runs yet"
          emptyDescription="Forecast runs appear here with their evaluation metrics."
          caption="Forecast run history"
        />
      </Card>

      <Modal
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        title={`Forecast run #${run?.id ?? ""}`}
        description="Exact parameters, windows and data provenance"
        width="max-w-2xl"
      >
        {run ? (
          <div className="space-y-3 text-[11.5px]">
            <div className="grid grid-cols-2 gap-2">
              <StatPill label="Data source" value={run.data_source} />
              <StatPill label="Products forecasted" value={formatNumber(run.products_forecasted)} />
              <StatPill label="Insufficient history" value={formatNumber(run.products_insufficient)} />
              <StatPill label="Created" value={formatDateTime(run.created_at)} />
            </div>
            <div>
              <p className="mb-1 font-medium text-ink">Notes</p>
              <p className="text-muted">{run.notes || "No additional notes were recorded for this run."}</p>
            </div>
            <div>
              <p className="mb-1 flex items-center gap-1 font-medium text-ink">
                <CheckCircle2 size={12} className="text-positive" aria-hidden /> Validation methodology
              </p>
              <ul className="list-disc space-y-0.5 pl-4 text-muted">
                <li>Rolling-origin splits: each fold trains only on data before its validation window.</li>
                <li>Metrics are MAE, RMSE and WAPE on the held-out folds (WAPE is skipped when demand is zero).</li>
                <li>The baseline is kept whenever no model beats it on validation.</li>
              </ul>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
