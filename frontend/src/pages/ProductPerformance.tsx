/** Product performance: ABC classes, growth, margin (only with cost data), variability. */

import { useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Info, Layers, Search, TrendingDown, TrendingUp } from "lucide-react";
import { useApp } from "../context/AppContext";
import { endpoints } from "../lib/api";
import { useApi, useDebounced } from "../lib/hooks";
import { formatCurrency, formatNumber, formatPercent } from "../lib/format";
import { DataTable } from "../components/DataTable";
import { FilterBar } from "../components/FilterBar";
import { DemoBanner, ErrorBanner } from "../components/Banners";
import { ForecastChart } from "../components/charts";
import {
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  LoadingBlock,
  Modal,
  Select,
  StatPill,
  cx,
} from "../components/ui";
import type { PerformanceRow } from "../lib/types";

export default function ProductPerformance() {
  const { filterParams, currency, filters } = useApp();
  const [search, setSearch] = useState("");
  const [abcFilter, setAbcFilter] = useState("");
  const [selected, setSelected] = useState<PerformanceRow | null>(null);
  const debounced = useDebounced(search);

  const performanceApi = useApi(() => endpoints.performance(filterParams), [JSON.stringify(filterParams)]);
  const historyApi = useApi(
    () =>
      selected
        ? endpoints.productHistory(selected.product_id, {
            granularity: "day",
            data_source: filters.data_source,
          })
        : Promise.resolve(null),
    [selected?.product_id, filters.data_source],
    { enabled: Boolean(selected) },
  );

  const data = performanceApi.data;
  const rows = useMemo(() => {
    let items = data?.items ?? [];
    if (debounced) {
      items = items.filter((row) =>
        `${row.name} ${row.sku} ${row.category ?? ""}`.toLowerCase().includes(debounced.toLowerCase()),
      );
    }
    if (abcFilter) items = items.filter((row) => row.abc_class === abcFilter);
    return items;
  }, [data, debounced, abcFilter]);

  const columns = useMemo(
    () => [
      {
        key: "name",
        header: "Product",
        sortable: true,
        value: (row: PerformanceRow) => row.name,
        render: (row: PerformanceRow) => (
          <button type="button" onClick={() => setSelected(row)} className="min-w-0 text-left">
            <p className="truncate font-medium text-ink underline decoration-dotted decoration-transparent hover:decoration-line">
              {row.name}
            </p>
            <p className="text-[10.5px] text-muted">
              {row.sku} · {row.category ?? "Uncategorised"}
            </p>
          </button>
        ),
      },
      {
        key: "abc",
        header: "ABC",
        align: "center" as const,
        value: (row: PerformanceRow) => row.abc_class ?? "",
        render: (row: PerformanceRow) => (
          <span title={`Cumulative revenue share ${row.cumulative_share ?? "—"}%`}>
            <Badge tone={row.abc_class === "A" ? "positive" : row.abc_class === "B" ? "accent" : "neutral"}>
              {row.abc_class ?? "—"}
            </Badge>
          </span>
        ),
        sortable: true,
      },
      {
        key: "revenue",
        header: "Revenue",
        align: "right" as const,
        sortable: true,
        value: (row: PerformanceRow) => row.revenue,
        render: (row: PerformanceRow) => formatCurrency(row.revenue, currency),
      },
      {
        key: "units",
        header: "Units",
        align: "right" as const,
        hideBelow: "sm" as const,
        sortable: true,
        value: (row: PerformanceRow) => row.units,
        render: (row: PerformanceRow) => formatNumber(row.units),
      },
      {
        key: "growth",
        header: "Growth",
        align: "right" as const,
        sortable: true,
        value: (row: PerformanceRow) => row.growth_pct ?? -999,
        render: (row: PerformanceRow) =>
          row.growth_pct === null ? (
            <span className="text-muted" title="No equivalent previous period">—</span>
          ) : (
            <span
              className={cx(
                "inline-flex items-center gap-0.5 font-medium",
                row.growth_pct > 0 ? "text-positive" : row.growth_pct < 0 ? "text-danger" : "text-muted",
              )}
            >
              {row.growth_pct > 0 ? <ArrowUpRight size={11} aria-hidden /> : <ArrowDownRight size={11} aria-hidden />}
              {formatPercent(row.growth_pct)}
            </span>
          ),
      },
      {
        key: "margin",
        header: "Gross margin",
        align: "right" as const,
        hideBelow: "md" as const,
        sortable: true,
        value: (row: PerformanceRow) => row.gross_margin ?? -999999,
        render: (row: PerformanceRow) =>
          row.cost_data_available && row.gross_margin !== null ? (
            <span title={`${row.gross_margin_pct?.toFixed(1)}% margin`}>{formatCurrency(row.gross_margin, currency)}</span>
          ) : (
            <span className="text-[10.5px] text-muted" title="Unit cost missing — margin cannot be calculated">
              no cost data
            </span>
          ),
      },
      {
        key: "variability",
        header: "Demand CV",
        align: "right" as const,
        hideBelow: "lg" as const,
        sortable: true,
        value: (row: PerformanceRow) => row.demand_variability ?? 0,
        render: (row: PerformanceRow) => (
          <span className="text-[11px]">
            {row.demand_variability === null ? "—" : row.demand_variability.toFixed(2)}
            {row.variability_label ? <span className="ml-1 text-muted">({row.variability_label})</span> : null}
          </span>
        ),
      },
      {
        key: "cover",
        header: "Cover",
        align: "right" as const,
        hideBelow: "lg" as const,
        sortable: true,
        value: (row: PerformanceRow) => row.days_of_cover ?? 0,
        render: (row: PerformanceRow) =>
          row.days_of_cover === null ? "—" : <span className={row.days_of_cover > 60 ? "text-warning" : ""}>{row.days_of_cover.toFixed(0)}d</span>,
      },
      {
        key: "flags",
        header: "Flags",
        render: (row: PerformanceRow) => (
          <div className="flex flex-wrap gap-1">
            {row.slow_moving ? <Badge tone="warning">slow-moving</Badge> : null}
            {row.days_since_last_sale !== null && row.days_since_last_sale > 30 ? (
              <Badge tone="neutral">{row.days_since_last_sale}d idle</Badge>
            ) : null}
            {!row.slow_moving && (row.days_since_last_sale === null || row.days_since_last_sale <= 30) ? (
              <span className="text-[10.5px] text-muted">—</span>
            ) : null}
          </div>
        ),
      },
    ],
    [currency],
  );

  const totalRevenue = (data?.items ?? []).reduce((sum, row) => sum + row.revenue, 0);

  return (
    <div className="space-y-4">
      <FilterBar />
      <DemoBanner demoSharePct={null} />
      {performanceApi.error ? <ErrorBanner error={performanceApi.error} /> : null}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <StatPill label="Revenue" value={formatCurrency(totalRevenue, currency)} />
        <StatPill
          label="Best seller"
          value={<span className="block truncate">{data?.flags.best_sellers[0] ?? "—"}</span>}
          tone="good"
        />
        <StatPill label="Slow-moving" value={data?.flags.slow_moving.length ?? 0} tone="warn" />
        <StatPill label="Negative growth" value={data?.flags.negative_growth_products ?? 0} tone="bad" />
        <StatPill
          label="Missing cost data"
          value={data?.flags.missing_cost_products ?? 0}
          tone={(data?.flags.missing_cost_products ?? 0) > 0 ? "warn" : "neutral"}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Card>
          <CardHeader title="ABC classification" description="Pareto split on cumulative revenue (A ≤ 80%, B ≤ 95%)" icon={<Layers size={15} aria-hidden />} />
          <div className="card-pad space-y-2">
            {(data?.abc_summary ?? []).map((row) => (
              <div key={row.abc_class} className="rounded-lg border border-line bg-elevated p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <Badge tone={row.abc_class === "A" ? "positive" : row.abc_class === "B" ? "accent" : "neutral"}>
                    Class {row.abc_class}
                  </Badge>
                  <span className="text-[11px] text-muted">{row.products} products</span>
                </div>
                <p className="mt-1 text-sm font-semibold tabular-nums">{formatCurrency(row.revenue, currency)}</p>
                <p className="text-[10.5px] text-muted">{formatNumber(row.units)} units sold</p>
              </div>
            ))}
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="Category contribution" description="Revenue and gross margin where cost data exists" />
          <DataTable
            rows={data?.category_summary ?? []}
            columns={[
              { key: "category", header: "Category", value: (row) => String(row.category), sortable: true },
              {
                key: "products",
                header: "Products",
                align: "right",
                value: (row) => Number(row.products),
                render: (row) => formatNumber(Number(row.products)),
                sortable: true,
              },
              {
                key: "revenue",
                header: "Revenue",
                align: "right",
                value: (row) => Number(row.revenue),
                render: (row) => formatCurrency(Number(row.revenue), currency),
                sortable: true,
              },
              {
                key: "margin",
                header: "Gross margin",
                align: "right",
                value: (row) => Number(row.margin ?? -1),
                render: (row) =>
                  row.margin === null ? <span className="text-[10.5px] text-muted">no cost data</span> : formatCurrency(Number(row.margin), currency),
                sortable: true,
              },
            ]}
            rowKey={(row) => String(row.category)}
            pageSize={6}
            initialSort={{ key: "revenue", dir: "desc" }}
            emptyTitle="No categories"
          />
        </Card>
      </div>

      <Callout tone="info" title="Margin is only shown when cost data exists">
        Products without a unit cost are labelled "no cost data" rather than being treated as unprofitable. Set unit costs on the
        product master (or import a cost column) to unlock margin analysis.
      </Callout>

      <Card>
        <CardHeader
          title="Product performance"
          description={`${rows.length} products · period ${data?.period.start_date ?? "—"} → ${data?.period.end_date ?? "—"}`}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
                <input
                  aria-label="Search products"
                  className="input w-40 pl-7 text-xs sm:w-56"
                  placeholder="Search…"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
              <Select aria-label="Filter by ABC class" className="w-28 text-xs" value={abcFilter} onChange={(event) => setAbcFilter(event.target.value)}>
                <option value="">All ABC</option>
                <option value="A">Class A</option>
                <option value="B">Class B</option>
                <option value="C">Class C</option>
              </Select>
            </div>
          }
        />
        {performanceApi.loading && !data ? (
          <LoadingBlock rows={6} />
        ) : (
          <DataTable
            rows={rows}
            columns={columns}
            rowKey={(row) => row.product_id}
            pageSize={12}
            initialSort={{ key: "revenue", dir: "desc" }}
            onRowClick={(row) => setSelected(row)}
            emptyTitle="No products in this period"
            emptyDescription="Adjust filters or import sales data."
            caption="Product performance table"
          />
        )}
      </Card>

      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected?.name ?? ""}
        description={`${selected?.sku ?? ""} · ${selected?.category ?? "Uncategorised"}`}
        width="max-w-3xl"
      >
        {selected ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <StatPill label="Revenue" value={formatCurrency(selected.revenue, currency)} />
              <StatPill label="Units" value={formatNumber(selected.units)} />
              <StatPill label="ABC class" value={selected.abc_class ?? "—"} />
              <StatPill
                label="Growth"
                value={selected.growth_pct === null ? "—" : formatPercent(selected.growth_pct)}
                tone={selected.growth_pct === null ? "neutral" : selected.growth_pct >= 0 ? "good" : "bad"}
              />
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <StatPill
                label="Gross margin"
                value={
                  selected.cost_data_available && selected.gross_margin !== null
                    ? formatCurrency(selected.gross_margin, currency)
                    : "no cost data"
                }
              />
              <StatPill label="Margin %" value={selected.gross_margin_pct !== null ? `${selected.gross_margin_pct.toFixed(1)}%` : "—"} />
              <StatPill label="Demand CV" value={selected.demand_variability !== null ? selected.demand_variability.toFixed(2) : "—"} />
              <StatPill label="Stock cover" value={selected.days_of_cover !== null ? `${selected.days_of_cover.toFixed(0)}d` : "—"} />
            </div>

            {historyApi.loading ? (
              <LoadingBlock rows={4} />
            ) : historyApi.data?.history?.length ? (
              <div className="rounded-lg border border-line p-2">
                <p className="mb-1 flex items-center gap-1 px-1 text-[11px] font-medium text-muted">
                  <TrendingUp size={12} aria-hidden /> Daily units sold
                </p>
                <ForecastChart
                  data={(historyApi.data.history as Array<{ period: string; units: number }>).map((point) => ({
                    period: point.period,
                    actual: point.units,
                    forecast: null,
                  }))}
                  height={220}
                />
              </div>
            ) : (
              <EmptyState title="No history in range" icon={<TrendingDown size={16} aria-hidden />} />
            )}

            <div className="rounded-lg border border-line bg-elevated p-2.5 text-[11px] text-muted">
              <p className="flex items-center gap-1 font-medium text-ink">
                <Info size={11} aria-hidden /> Interpretation
              </p>
              <p className="mt-1">
                {selected.slow_moving
                  ? `Flagged slow-moving: last sale ${selected.days_since_last_sale ?? "?"} days ago with ${selected.days_of_cover?.toFixed(0) ?? "?"} days of cover.`
                  : "Selling steadily — no slow-moving flag."}{" "}
                {selected.demand_variability !== null && selected.demand_variability > 0.5
                  ? "Demand is volatile, so safety stock should be generous."
                  : "Demand is relatively steady."}
              </p>
              {selected.previous_revenue !== null ? (
                <p className="mt-1">
                  Previous equivalent period revenue: {formatCurrency(selected.previous_revenue, currency)} →{" "}
                  {formatCurrency(selected.revenue, currency)}.
                </p>
              ) : null}
            </div>
            <div className="flex justify-end">
              <Button variant="secondary" onClick={() => setSelected(null)}>
                Close
              </Button>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
