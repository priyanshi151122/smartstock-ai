/** Executive overview: KPIs, trends, product leaders, inventory risk. */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Boxes,
  TrendingUp,
  TruckIcon,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { endpoints, toApiError } from "../lib/api";
import { useApi } from "../lib/hooks";
import { formatCurrency, formatNumber, formatPercent } from "../lib/format";
import { CategoryBarChart, SalesTrendChart, StockVsForecastChart } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterBar } from "../components/FilterBar";
import { KpiGrid } from "../components/KpiGrid";
import { DemoBanner, DemoDataAvailable, ErrorBanner, OnboardingChecklist } from "../components/Banners";
import { Badge, Button, Card, CardHeader, EmptyState, LoadingBlock, RiskBadge, StatPill, cx } from "../components/ui";
import type { InventoryRiskItem, ProductSalesRow } from "../lib/types";

export default function Overview() {
  const { filters, filterParams, currency, refreshMeta, pushToast, meta, refreshSettings } = useApp();
  const dashboard = useApi(() => endpoints.dashboard(filterParams), [JSON.stringify(filterParams)]);
  const [loadingDemo, setLoadingDemo] = useState(false);

  const loadDemo = async () => {
    setLoadingDemo(true);
    try {
      await endpoints.loadDemo();
      pushToast({ tone: "success", title: "Demo dataset loaded", description: "Synthetic rows are labelled as demo data." });
      refreshMeta();
      refreshSettings();
      dashboard.reload();
    } catch (error) {
      const apiError = toApiError(error);
      pushToast({ tone: "error", title: apiError.message });
    } finally {
      setLoadingDemo(false);
    }
  };

  const data = dashboard.data;
  const kpis = data?.kpis;
  const risk = data?.inventory_risk;

  const topColumns = useMemo(
    () => [
      {
        key: "name",
        header: "Product",
        value: (row: ProductSalesRow) => row.name,
        render: (row: ProductSalesRow) => (
          <div className="min-w-0">
            <p className="truncate font-medium text-ink">{row.name}</p>
            <p className="text-[10.5px] text-muted">
              {row.sku} · {row.category ?? "Uncategorised"}
            </p>
          </div>
        ),
        sortable: true,
      },
      {
        key: "units",
        header: "Units",
        align: "right" as const,
        value: (row: ProductSalesRow) => row.units,
        render: (row: ProductSalesRow) => formatNumber(row.units),
        sortable: true,
      },
      {
        key: "revenue",
        header: "Revenue",
        align: "right" as const,
        value: (row: ProductSalesRow) => row.revenue,
        render: (row: ProductSalesRow) => formatCurrency(row.revenue, currency),
        sortable: true,
      },
      {
        key: "share",
        header: "Share",
        align: "right" as const,
        hideBelow: "sm" as const,
        value: (row: ProductSalesRow) => row.share_of_revenue ?? 0,
        render: (row: ProductSalesRow) => (row.share_of_revenue !== null ? `${row.share_of_revenue.toFixed(1)}%` : "—"),
        sortable: true,
      },
      {
        key: "abc",
        header: "ABC",
        align: "center" as const,
        hideBelow: "md" as const,
        value: (row: ProductSalesRow) => row.abc_class,
        render: (row: ProductSalesRow) => (
          <Badge tone={row.abc_class === "A" ? "positive" : row.abc_class === "B" ? "accent" : "neutral"}>
            {row.abc_class ?? "—"}
          </Badge>
        ),
        sortable: true,
      },
    ],
    [currency],
  );

  const riskColumns = useMemo(
    () => [
      {
        key: "name",
        header: "Product",
        value: (row: InventoryRiskItem) => row.name,
        render: (row: InventoryRiskItem) => (
          <div className="min-w-0">
            <p className="truncate font-medium text-ink">{row.name}</p>
            <p className="text-[10.5px] text-muted">{row.sku}</p>
          </div>
        ),
        sortable: true,
      },
      {
        key: "risk",
        header: "Risk",
        value: (row: InventoryRiskItem) => row.risk_level,
        render: (row: InventoryRiskItem) => <RiskBadge level={row.risk_level} />,
        sortable: true,
      },
      {
        key: "stock",
        header: "Stock",
        align: "right" as const,
        value: (row: InventoryRiskItem) => row.current_stock,
        render: (row: InventoryRiskItem) => formatNumber(row.current_stock),
        sortable: true,
      },
      {
        key: "cover",
        header: "Cover",
        align: "right" as const,
        hideBelow: "sm" as const,
        value: (row: InventoryRiskItem) => row.coverage_days ?? 0,
        render: (row: InventoryRiskItem) => (row.coverage_days !== null ? `${row.coverage_days.toFixed(1)}d` : "—"),
        sortable: true,
      },
      {
        key: "rop",
        header: "Reorder pt.",
        align: "right" as const,
        hideBelow: "md" as const,
        value: (row: InventoryRiskItem) => row.reorder_point,
        render: (row: InventoryRiskItem) => formatNumber(row.reorder_point, 1),
        sortable: true,
      },
    ],
    [],
  );

  const hasData = kpis?.has_data ?? false;

  return (
    <div className="space-y-4">
      <FilterBar />
      <DemoBanner demoSharePct={kpis?.demo_share_pct} />
      <DemoDataAvailable onLoad={loadDemo} loading={loadingDemo} />

      {dashboard.error ? <ErrorBanner error={dashboard.error} /> : null}

      {!dashboard.loading && !hasData && !dashboard.error ? (
        <Card>
          <EmptyState
            title="No sales records match these filters"
            description="Import a CSV/XLSX sales file, widen the date range, or clear the filters. Every KPI below is calculated from stored rows only."
            icon={<Boxes size={18} aria-hidden />}
            action={
              <div className="flex gap-2">
                <Link to="/import" className="btn-primary px-3 py-1.5 text-xs">
                  Import sales data
                </Link>
                <Button size="sm" variant="secondary" onClick={loadDemo} loading={loadingDemo}>
                  Load demo dataset
                </Button>
              </div>
            }
          />
        </Card>
      ) : null}

      <KpiGrid cards={kpis?.cards ?? []} loading={dashboard.loading} />

      {kpis ? (
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
          <Badge tone="neutral">{kpis.period.label}</Badge>
          <span>{kpis.period.active_days} trading days with records</span>
          <span aria-hidden>·</span>
          <span>
            Source:{" "}
            {kpis.data_source === "demo" ? "synthetic demo dataset" : filters.data_source === "actual" ? "real imported records" : "all persisted rows"}
          </span>
          <span aria-hidden>·</span>
          <span>Computed {new Date(kpis.generated_at).toLocaleTimeString("en-IN")}</span>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Sales over time"
            description={`Aggregated by ${data?.granularity ?? "day"} · revenue and units`}
            icon={<Activity size={15} aria-hidden />}
            actions={
              <Link to="/sales" className="btn-ghost px-2 py-1 text-[11px]">
                Details <ArrowRight size={12} aria-hidden />
              </Link>
            }
          />
          {dashboard.loading && !data ? (
            <LoadingBlock rows={5} />
          ) : data?.sales_over_time.length ? (
            <div className="card-pad">
              <SalesTrendChart data={data.sales_over_time} granularity={data.granularity} />
            </div>
          ) : (
            <EmptyState title="No trend data" description="The selected period has no sales rows." />
          )}
        </Card>

        <Card>
          <CardHeader title="Revenue by category" description="Share of revenue in the selected period" />
          {dashboard.loading && !data ? (
            <LoadingBlock rows={5} />
          ) : data?.revenue_by_category.length ? (
            <div className="card-pad">
              <CategoryBarChart data={data.revenue_by_category} />
              <ul className="mt-2 space-y-1 text-[11px]">
                {data.revenue_by_category.slice(0, 4).map((row) => (
                  <li key={row.category} className="flex items-center justify-between gap-2">
                    <span className="truncate text-muted">{row.category}</span>
                    <span className="tabular-nums text-ink">{row.share.toFixed(1)}%</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <EmptyState title="No category data" description="Sales rows in this period have no category." />
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Current stock vs forecast demand"
            description={
              risk?.demand_source === "forecast"
                ? "Demand from the latest forecast run"
                : "No forecast yet — demand uses trailing 28-day sales"
            }
            icon={<TrendingUp size={15} aria-hidden />}
            actions={
              <Link to="/forecast" className="btn-ghost px-2 py-1 text-[11px]">
                Forecast <ArrowRight size={12} aria-hidden />
              </Link>
            }
          />
          {data?.stock_vs_forecast.length ? (
            <div className="card-pad">
              <StockVsForecastChart data={data.stock_vs_forecast} />
            </div>
          ) : (
            <EmptyState
              title="No products to compare"
              description="Add products with stock levels to see cover against demand."
            />
          )}
        </Card>

        <div className="space-y-3">
          <Card>
            <CardHeader title="Inventory risk summary" icon={<AlertTriangle size={15} aria-hidden />} />
            <div className="card-pad space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <StatPill label="Stockout" value={risk?.counts.stockout ?? 0} tone="bad" />
                <StatPill label="High risk" value={risk?.counts.high ?? 0} tone="warn" />
                <StatPill label="Medium" value={risk?.counts.medium ?? 0} />
                <StatPill label="Overstock" value={risk?.counts.overstock ?? 0} tone="warn" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <StatPill
                  label="Stock value"
                  value={
                    risk?.summary.inventory_value !== null && risk?.summary.inventory_value !== undefined
                      ? formatCurrency(risk.summary.inventory_value, currency)
                      : "—"
                  }
                />
                <StatPill
                  label="Avg cover"
                  value={risk?.summary.avg_cover_days !== null && risk?.summary.avg_cover_days !== undefined ? `${risk.summary.avg_cover_days}d` : "—"}
                />
              </div>
              <Link to="/reorder" className="btn-secondary w-full py-1.5 text-xs">
                Review reorder recommendations <ArrowRight size={12} aria-hidden />
              </Link>
            </div>
          </Card>

          {data?.onboarding ? (
            <OnboardingChecklist
              steps={data.onboarding.steps}
              completed={data.onboarding.completed}
              total={data.onboarding.total}
            />
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Top-selling products"
            description="By revenue in the selected period"
            actions={<Badge tone="positive">Leaders</Badge>}
          />
          <DataTable
            rows={data?.top_products ?? []}
            columns={topColumns}
            rowKey={(row) => row.product_id}
            initialSort={{ key: "revenue", dir: "desc" }}
            pageSize={6}
            emptyTitle="No products sold yet"
            caption="Top selling products"
          />
        </Card>

        <Card>
          <CardHeader
            title="Lowest-selling products"
            description="Candidates for promotion or delisting"
            actions={<Badge tone="warning">Watchlist</Badge>}
          />
          <DataTable
            rows={data?.low_products ?? []}
            columns={topColumns}
            rowKey={(row) => row.product_id}
            initialSort={{ key: "units", dir: "asc" }}
            pageSize={6}
            emptyTitle="No products sold yet"
            caption="Lowest selling products"
          />
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Products needing attention"
          description="Ranked by risk severity, then stock on hand"
          icon={<TruckIcon size={15} aria-hidden />}
          actions={
            <Link to="/inventory" className="btn-ghost px-2 py-1 text-[11px]">
              Inventory <ArrowRight size={12} aria-hidden />
            </Link>
          }
        />
        <DataTable
          rows={(risk?.items ?? []).filter((item) => item.risk_level !== "low")}
          columns={riskColumns}
          rowKey={(row) => row.product_id}
          initialSort={{ key: "risk", dir: "asc" }}
          pageSize={8}
          emptyTitle="No stock risks detected"
          emptyDescription="Every product has healthy cover relative to demand."
          caption="Inventory risk table"
        />
      </Card>

      {data?.forecast_run ? (
        <Card className="card-pad">
          <div className="flex flex-wrap items-center gap-3 text-[11.5px] text-muted">
            <span className={cx("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5", "border-line bg-elevated text-ink")}>
              <TrendingUp size={12} aria-hidden /> Latest forecast #{data.forecast_run.id}
            </span>
            <span>{data.forecast_run.horizon_days}-day horizon</span>
            <span aria-hidden>·</span>
            <span>Model: {data.forecast_run.model_used ?? "—"}</span>
            {data.forecast_run.summary_metrics ? (
              <>
                <span aria-hidden>·</span>
                <span>
                  Validation WAPE{" "}
                  {typeof (data.forecast_run.summary_metrics as { selected?: { wape?: number | null } }).selected?.wape === "number"
                    ? formatPercent(
                        ((data.forecast_run.summary_metrics as { selected: { wape: number } }).selected.wape ?? 0) * 100,
                        1,
                      ).replace("+", "")
                    : "—"}
                </span>
              </>
            ) : null}
            <span className="ml-auto text-[10.5px]">{meta?.latest_forecast_at ? `Trained ${new Date(meta.latest_forecast_at).toLocaleString("en-IN")}` : ""}</span>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
