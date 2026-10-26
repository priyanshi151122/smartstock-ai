/** Shared date-range / category / product / data-source filter bar. */

import { CalendarDays, ChevronDown, Download, Filter, RotateCcw, Search } from "lucide-react";
import { useApp, type FilterPreset } from "../context/AppContext";
import { Badge, Button, Select, TextInput, cx } from "./ui";
import { useDebounced } from "../lib/hooks";
import { useEffect, useState } from "react";

const PRESETS: Array<{ key: FilterPreset; label: string }> = [
  { key: "7d", label: "7 days" },
  { key: "30d", label: "30 days" },
  { key: "90d", label: "90 days" },
  { key: "12m", label: "12 months" },
  { key: "all", label: "All time" },
];

export interface FilterBarProps {
  showProduct?: boolean;
  onExport?: () => void;
  exportLabel?: string;
  extra?: React.ReactNode;
}

export function FilterBar({ showProduct = false, onExport, exportLabel = "Export", extra }: FilterBarProps) {
  const { filters, applyPreset, setFilters, resetFilters, meta } = useApp();
  const [expanded, setExpanded] = useState(false);
  const [productQuery, setProductQuery] = useState("");
  const [products, setProducts] = useState<Array<{ id: number; name: string; sku: string }>>([]);
  const debounced = useDebounced(productQuery, 300);

  useEffect(() => {
    if (!showProduct) return;
    let cancelled = false;
    import("../lib/api").then(({ endpoints }) =>
      endpoints
        .products({ search: debounced, page_size: 12, sort_by: "name" })
        .then((data: { items: Array<{ id: number; name: string; sku: string }> }) => {
          if (!cancelled) setProducts(data.items ?? []);
        })
        .catch(() => undefined),
    );
    return () => {
      cancelled = true;
    };
  }, [debounced, showProduct]);

  const activeCount =
    (filters.category ? 1 : 0) + (filters.product_id ? 1 : 0) + (filters.data_source ? 1 : 0);

  return (
    <div className="card mb-4 p-3">
      <div className="mb-2 flex items-center justify-between gap-2 lg:hidden">
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="btn-secondary px-2.5 py-1.5 text-xs"
          aria-expanded={expanded}
          aria-controls="filter-fields"
        >
          <Filter size={13} aria-hidden /> Filters
          {activeCount > 0 ? <span className="rounded-full bg-accent px-1.5 text-[10px] text-white dark:text-slate-950">{activeCount}</span> : null}
          <ChevronDown size={13} className={cx("transition-transform", expanded && "rotate-180")} aria-hidden />
        </button>
        <span className="truncate text-[11px] text-muted">
          {filters.preset === "custom" ? "Custom range" : PRESETS.find((preset) => preset.key === filters.preset)?.label ?? "Period"}
          {filters.category ? ` · ${filters.category}` : ""}
        </span>
      </div>
      <div className={cx("flex-col gap-3 lg:flex lg:flex-row lg:items-end lg:justify-between", expanded ? "flex" : "hidden lg:flex")} id="filter-fields">
        <div className="grid flex-1 grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="label" htmlFor="filter-preset">
              <span className="inline-flex items-center gap-1">
                <CalendarDays size={11} aria-hidden /> Period
              </span>
            </label>
            <Select
              id="filter-preset"
              value={filters.preset}
              onChange={(event) => applyPreset(event.target.value as FilterPreset)}
            >
              {PRESETS.map((preset) => (
                <option key={preset.key} value={preset.key}>
                  {preset.label}
                </option>
              ))}
              <option value="custom">Custom range</option>
            </Select>
          </div>

          <div>
            <label className="label" htmlFor="filter-start">
              From
            </label>
            <TextInput
              id="filter-start"
              type="date"
              value={filters.start_date ?? ""}
              max={filters.end_date ?? undefined}
              onChange={(event) => setFilters({ start_date: event.target.value || null, preset: "custom" })}
            />
          </div>

          <div>
            <label className="label" htmlFor="filter-end">
              To
            </label>
            <TextInput
              id="filter-end"
              type="date"
              value={filters.end_date ?? ""}
              min={filters.start_date ?? undefined}
              onChange={(event) => setFilters({ end_date: event.target.value || null, preset: "custom" })}
            />
          </div>

          <div>
            <label className="label" htmlFor="filter-category">
              Category
            </label>
            <Select
              id="filter-category"
              value={filters.category ?? ""}
              onChange={(event) => setFilters({ category: event.target.value || null })}
            >
              <option value="">All categories</option>
              {(meta?.categories ?? []).map((category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ))}
            </Select>
          </div>

          {showProduct ? (
            <div className="sm:col-span-2">
              <label className="label" htmlFor="filter-product">
                <span className="inline-flex items-center gap-1">
                  <Search size={11} aria-hidden /> Product
                </span>
              </label>
              <div className="flex gap-2">
                <TextInput
                  id="filter-product"
                  placeholder="Search product name or SKU…"
                  value={productQuery}
                  onChange={(event) => setProductQuery(event.target.value)}
                />
                <Select
                  aria-label="Matching products"
                  value={filters.product_id ?? ""}
                  onChange={(event) =>
                    setFilters({ product_id: event.target.value ? Number(event.target.value) : null })
                  }
                >
                  <option value="">All products</option>
                  {products.map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.name} ({product.sku})
                    </option>
                  ))}
                </Select>
              </div>
            </div>
          ) : null}

          <div>
            <label className="label" htmlFor="filter-source">
              Data source
            </label>
            <Select
              id="filter-source"
              value={filters.data_source ?? ""}
              onChange={(event) =>
                setFilters({ data_source: (event.target.value || null) as "actual" | "demo" | null })
              }
            >
              <option value="">All records</option>
              <option value="actual">Real imported records</option>
              <option value="demo">Synthetic demo data</option>
            </Select>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {activeCount > 0 ? <Badge tone="accent">{activeCount} filter{activeCount > 1 ? "s" : ""} active</Badge> : null}
          {extra}
          <Button
            variant="ghost"
            size="sm"
            onClick={resetFilters}
            icon={<RotateCcw size={13} aria-hidden />}
            aria-label="Reset all filters"
          >
            Reset
          </Button>
          {onExport ? (
            <Button size="sm" onClick={onExport} icon={<Download size={13} aria-hidden />}>
              {exportLabel}
            </Button>
          ) : null}
        </div>
      </div>

      {filters.category || filters.product_id || filters.data_source ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-line pt-2 text-[11px] text-muted">
          <Filter size={11} aria-hidden />
          <span>Active:</span>
          {filters.category ? (
            <button type="button" className="chip hover:text-ink" onClick={() => setFilters({ category: null })}>
              {filters.category} ✕
            </button>
          ) : null}
          {filters.product_id ? (
            <button type="button" className="chip hover:text-ink" onClick={() => setFilters({ product_id: null })}>
              product #{filters.product_id} ✕
            </button>
          ) : null}
          {filters.data_source ? (
            <button type="button" className="chip hover:text-ink" onClick={() => setFilters({ data_source: null })}>
              {filters.data_source === "demo" ? "demo data" : "real records"} ✕
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function SectionTitle({
  title,
  subtitle,
  actions,
  className,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("mb-3 flex flex-wrap items-end justify-between gap-2", className)}>
      <div>
        <h2 className="text-[15px] font-semibold">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-muted">{subtitle}</p> : null}
      </div>
      {actions}
    </div>
  );
}
