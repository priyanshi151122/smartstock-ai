/** Sales analytics: trends, category split, product table with search/sort/paging. */

import { useMemo, useState } from "react";
import { BarChart3, Download, Search } from "lucide-react";
import { useApp } from "../context/AppContext";
import { endpoints, toApiError } from "../lib/api";
import { useApi, useDebounced } from "../lib/hooks";
import { formatCurrency, formatNumber } from "../lib/format";
import { CategoryBarChart, SalesTrendChart } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterBar, SectionTitle } from "../components/FilterBar";
import { DemoBanner, ErrorBanner } from "../components/Banners";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  LoadingBlock,
  Select,
  StatPill,
  TextInput,
} from "../components/ui";
import type { SalesResponse } from "../lib/types";

type ProductRow = SalesResponse["products"][number];

const GRANULARITIES = [
  { key: "day", label: "Daily" },
  { key: "week", label: "Weekly" },
  { key: "month", label: "Monthly" },
];

export default function SalesAnalytics() {
  const { filterParams, currency, pushToast } = useApp();
  const [granularity, setGranularity] = useState<"day" | "week" | "month">("week");
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search);
  const [sortKey, setSortKey] = useState<"revenue" | "units" | "name">("revenue");

  const sales = useApi(
    () => endpoints.sales({ ...filterParams, granularity, limit: 200 }),
    [JSON.stringify(filterParams), granularity],
  );

  const data = sales.data;
  const rows = useMemo(() => {
    const items = data?.products ?? [];
    const filtered = debouncedSearch
      ? items.filter((row) =>
          `${row.name} ${row.sku} ${row.category ?? ""}`.toLowerCase().includes(debouncedSearch.toLowerCase()),
        )
      : items;
    return [...filtered].sort((a, b) => {
      if (sortKey === "name") return a.name.localeCompare(b.name);
      return Number(b[sortKey] ?? 0) - Number(a[sortKey] ?? 0);
    });
  }, [data, debouncedSearch, sortKey]);

  const exportCsv = async () => {
    try {
      await endpoints.generateReport({
        report_type: "sales_summary",
        file_format: "xlsx",
        start_date: filterParams.start_date,
        end_date: filterParams.end_date,
        category: filterParams.category,
        product_id: filterParams.product_id,
        data_source: filterParams.data_source,
      });
      pushToast({
        tone: "success",
        title: "Sales report generated",
        description: "Download it from the Reports & Exports page.",
      });
    } catch (error) {
      pushToast({ tone: "error", title: toApiError(error).message });
    }
  };

  const totals = data?.totals;
  const columns = useMemo(
    () => [
      {
        key: "name",
        header: "Product",
        sortable: true,
        value: (row: ProductRow) => row.name,
        render: (row: ProductRow) => (
          <div className="min-w-0">
            <p className="truncate font-medium">{row.name}</p>
            <p className="text-[10.5px] text-muted">
              {row.sku} · {row.category ?? "Uncategorised"}
            </p>
          </div>
        ),
      },
      {
        key: "units",
        header: "Units",
        align: "right" as const,
        sortable: true,
        value: (row: ProductRow) => row.units,
        render: (row: ProductRow) => formatNumber(row.units, 0),
      },
      {
        key: "revenue",
        header: "Revenue",
        align: "right" as const,
        sortable: true,
        value: (row: ProductRow) => row.revenue,
        render: (row: ProductRow) => formatCurrency(row.revenue, currency),
      },
      {
        key: "avg_price",
        header: "Avg price",
        align: "right" as const,
        hideBelow: "md" as const,
        value: (row: ProductRow) => row.avg_price ?? 0,
        render: (row: ProductRow) => (row.avg_price === null ? "—" : formatCurrency(row.avg_price, currency)),
      },
      {
        key: "orders",
        header: "Orders",
        align: "right" as const,
        hideBelow: "lg" as const,
        value: (row: ProductRow) => row.orders,
        render: (row: ProductRow) => formatNumber(row.orders, 0),
      },
      {
        key: "abc_class",
        header: "ABC",
        align: "center" as const,
        hideBelow: "sm" as const,
        value: (row: ProductRow) => row.abc_class ?? "",
        render: (row: ProductRow) => (
          <Badge tone={row.abc_class === "A" ? "positive" : row.abc_class === "B" ? "accent" : "neutral"}>
            {row.abc_class ?? "—"}
          </Badge>
        ),
      },
    ],
    [currency],
  );

  return (
    <div className="space-y-4">
      <FilterBar onExport={exportCsv} exportLabel="Export report" />
      <DemoBanner demoSharePct={null} />
      {sales.error ? <ErrorBanner error={sales.error} /> : null}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <StatPill label="Revenue" value={formatCurrency(totals?.revenue ?? 0, currency)} />
        <StatPill label="Units" value={formatNumber(totals?.units ?? 0)} />
        <StatPill label="Products" value={formatNumber(totals?.products ?? 0)} />
        <StatPill label="Trading days" value={formatNumber(totals?.active_days ?? 0)} />
        <StatPill label="Records" value={formatNumber(totals?.rows ?? 0)} />
      </div>

      <Card>
        <CardHeader
          title="Revenue and units over time"
          description={data?.period ? `${data.period.start_date ?? "start"} → ${data.period.end_date ?? "end"}` : "Loading…"}
          icon={<BarChart3 size={15} aria-hidden />}
          actions={
            <div className="flex rounded-lg border border-line p-0.5" role="group" aria-label="Chart granularity">
              {GRANULARITIES.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => setGranularity(option.key as "day" | "week" | "month")}
                  aria-pressed={granularity === option.key}
                  className={
                    granularity === option.key
                      ? "rounded-md bg-accent px-2.5 py-1 text-[11px] font-medium text-white dark:text-slate-950"
                      : "rounded-md px-2.5 py-1 text-[11px] text-muted hover:text-ink"
                  }
                >
                  {option.label}
                </button>
              ))}
            </div>
          }
        />
        {sales.loading && !data ? (
          <LoadingBlock rows={6} />
        ) : data?.series.length ? (
          <div className="card-pad">
            <SalesTrendChart data={data.series} granularity={granularity} height={320} />
          </div>
        ) : (
          <EmptyState title="No sales in this period" description="Adjust the date range or import more data." />
        )}
      </Card>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader title="Revenue by category" description="Hover a bar for exact values" />
          {data?.categories.length ? (
            <div className="card-pad">
              <CategoryBarChart data={data.categories} />
            </div>
          ) : (
            <EmptyState title="No categories" />
          )}
        </Card>

        <Card>
          <CardHeader title="Category performance" description="Revenue, units and share" />
          <DataTable
            rows={data?.categories ?? []}
            columns={[
              { key: "category", header: "Category", value: (row) => String(row.category), sortable: true },
              {
                key: "revenue",
                header: "Revenue",
                align: "right",
                sortable: true,
                value: (row) => Number(row.revenue),
                render: (row) => formatCurrency(Number(row.revenue), currency),
              },
              {
                key: "units",
                header: "Units",
                align: "right",
                sortable: true,
                value: (row) => Number(row.units),
                render: (row) => formatNumber(Number(row.units)),
              },
              {
                key: "share",
                header: "Share",
                align: "right",
                sortable: true,
                value: (row) => Number(row.share),
                render: (row) => `${Number(row.share).toFixed(1)}%`,
              },
            ]}
            rowKey={(row) => String(row.category)}
            pageSize={8}
            initialSort={{ key: "revenue", dir: "desc" }}
            emptyTitle="No category data"
          />
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Product sales"
          description={`${rows.length} products in scope · sort by any column`}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
                <TextInput
                  aria-label="Search products"
                  placeholder="Search…"
                  className="w-40 pl-7 text-xs sm:w-56"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
              <Select
                aria-label="Sort products"
                className="w-32 text-xs"
                value={sortKey}
                onChange={(event) => setSortKey(event.target.value as "revenue" | "units" | "name")}
              >
                <option value="revenue">Revenue</option>
                <option value="units">Units</option>
                <option value="name">Name</option>
              </Select>
              <Button size="sm" variant="secondary" onClick={exportCsv} icon={<Download size={13} aria-hidden />}>
                XLSX
              </Button>
            </div>
          }
        />
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(row) => row.product_id}
          pageSize={12}
          initialSort={{ key: "revenue", dir: "desc" }}
          emptyTitle="No products match"
          emptyDescription={debouncedSearch ? "Try a different search term." : "No sales recorded in this period."}
          caption="Product sales table"
        />
      </Card>

      <SectionTitle
        title="How these numbers are calculated"
        subtitle="Revenue = quantity × unit price for every stored row in the selected period; ABC classes use cumulative revenue contribution (80/95 cut-offs)."
      />
    </div>
  );
}
