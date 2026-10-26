/** Inventory management: stock levels, configuration, audited adjustments, ledger. */

import { useMemo, useState } from "react";
import { Boxes, History, PackagePlus, Search, Settings2, TriangleAlert } from "lucide-react";
import { useApp } from "../context/AppContext";
import { endpoints, toApiError } from "../lib/api";
import { useApi, useDebounced } from "../lib/hooks";
import { formatCurrency, formatDateTime, formatNumber } from "../lib/format";
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
  RiskBadge,
  Select,
  StatPill,
  StatusBadge,
  TextInput,
} from "../components/ui";
import type { InventoryRow, StockMovement } from "../lib/types";

export default function Inventory() {
  const { filters, currency, pushToast, refreshMeta } = useApp();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const debouncedSearch = useDebounced(search);

  const [adjustRow, setAdjustRow] = useState<InventoryRow | null>(null);
  const [configRow, setConfigRow] = useState<InventoryRow | null>(null);
  const [ledgerProduct, setLedgerProduct] = useState<InventoryRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [adjustForm, setAdjustForm] = useState({ quantity_delta: 0, reason: "", actor: "store-manager", reference: "" });
  const [configForm, setConfigForm] = useState({
    reorder_threshold: 0,
    lead_time_days: 7,
    min_order_qty: 1,
    pack_size: 1,
    safety_stock_days: 3,
    review_period_days: 7,
    current_stock: 0,
  });

  const inventoryApi = useApi(
    () =>
      endpoints.inventory({
        page,
        page_size: 12,
        search: debouncedSearch,
        category: filters.category,
        data_source: filters.data_source,
        sort_by: sortBy,
        sort_dir: sortDir,
      }),
    [page, debouncedSearch, filters.category, filters.data_source, sortBy, sortDir],
  );

  const movementsApi = useApi(
    () => endpoints.movements({ product_id: ledgerProduct?.product_id, limit: 50 }),
    [ledgerProduct?.product_id],
    { enabled: Boolean(ledgerProduct) },
  );

  const data = inventoryApi.data;
  const summary = data?.summary;

  const openAdjust = (row: InventoryRow) => {
    setAdjustRow(row);
    setFormError(null);
    setAdjustForm({ quantity_delta: 0, reason: "", actor: "store-manager", reference: "" });
  };

  const openConfig = (row: InventoryRow) => {
    setConfigRow(row);
    setFormError(null);
    setConfigForm({
      reorder_threshold: row.reorder_threshold,
      lead_time_days: row.lead_time_days,
      min_order_qty: row.min_order_qty,
      pack_size: row.pack_size,
      safety_stock_days: row.safety_stock_days,
      review_period_days: row.review_period_days,
      current_stock: row.current_stock,
    });
  };

  const submitAdjust = async () => {
    if (!adjustRow) return;
    if (!adjustForm.reason.trim() || adjustForm.reason.trim().length < 3) {
      setFormError("Add a short reason (at least 3 characters) so the change is auditable.");
      return;
    }
    if (!adjustForm.quantity_delta) {
      setFormError("Enter a non-zero quantity change (positive for receipts, negative for shrinkage).");
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      const updated = await endpoints.adjustStock(adjustRow.product_id, {
        quantity_delta: Number(adjustForm.quantity_delta),
        reason: adjustForm.reason.trim(),
        actor: adjustForm.actor || "store-manager",
        reference: adjustForm.reference || undefined,
      });
      pushToast({
        tone: "success",
        title: "Stock adjusted",
        description: `${adjustRow.name}: ${adjustRow.current_stock} → ${updated.current_stock} units. Movement recorded in the ledger.`,
      });
      setAdjustRow(null);
      inventoryApi.reload();
      refreshMeta();
    } catch (error) {
      setFormError(toApiError(error).message);
    } finally {
      setBusy(false);
    }
  };

  const submitConfig = async () => {
    if (!configRow) return;
    setBusy(true);
    setFormError(null);
    try {
      await endpoints.updateInventory(configRow.product_id, {
        reorder_threshold: Number(configForm.reorder_threshold),
        lead_time_days: Number(configForm.lead_time_days),
        min_order_qty: Number(configForm.min_order_qty),
        pack_size: Number(configForm.pack_size),
        safety_stock_days: Number(configForm.safety_stock_days),
        review_period_days: Number(configForm.review_period_days),
        current_stock: Number(configForm.current_stock),
      });
      pushToast({ tone: "success", title: "Inventory rules updated", description: configRow.name });
      setConfigRow(null);
      inventoryApi.reload();
    } catch (error) {
      setFormError(toApiError(error).message);
    } finally {
      setBusy(false);
    }
  };

  const columns = useMemo(
    () => [
      {
        key: "name",
        header: "Product",
        sortable: true,
        value: (row: InventoryRow) => row.name,
        render: (row: InventoryRow) => (
          <div className="min-w-0">
            <p className="truncate font-medium text-ink">{row.name}</p>
            <p className="text-[10.5px] text-muted">
              {row.sku} · {row.category ?? "Uncategorised"}
            </p>
          </div>
        ),
      },
      {
        key: "risk",
        header: "Risk",
        value: (row: InventoryRow) => row.risk_level,
        render: (row: InventoryRow) => <RiskBadge level={row.risk_level} />,
        sortable: true,
      },
      {
        key: "current_stock",
        header: "Stock",
        align: "right" as const,
        sortable: true,
        value: (row: InventoryRow) => row.current_stock,
        render: (row: InventoryRow) => (
          <span className={row.current_stock <= 0 ? "font-medium text-danger" : ""}>{formatNumber(row.current_stock)}</span>
        ),
      },
      {
        key: "reorder_threshold",
        header: "Reorder pt.",
        align: "right" as const,
        hideBelow: "md" as const,
        sortable: true,
        value: (row: InventoryRow) => row.reorder_threshold,
        render: (row: InventoryRow) => formatNumber(row.reorder_threshold),
      },
      {
        key: "cover",
        header: "Cover",
        align: "right" as const,
        hideBelow: "sm" as const,
        value: (row: InventoryRow) => row.days_of_cover ?? 0,
        render: (row: InventoryRow) => (row.days_of_cover === null ? "—" : `${row.days_of_cover.toFixed(1)}d`),
        sortable: true,
      },
      {
        key: "lead",
        header: "Lead time",
        align: "right" as const,
        hideBelow: "lg" as const,
        value: (row: InventoryRow) => row.lead_time_days,
        render: (row: InventoryRow) => `${row.lead_time_days}d`,
        sortable: true,
      },
      {
        key: "value",
        header: "Stock value",
        align: "right" as const,
        hideBelow: "lg" as const,
        value: (row: InventoryRow) => row.stock_value ?? 0,
        render: (row: InventoryRow) =>
          row.stock_value === null ? <span title="Requires unit cost">—</span> : formatCurrency(row.stock_value, currency),
        sortable: true,
      },
      {
        key: "actions",
        header: "Actions",
        align: "right" as const,
        render: (row: InventoryRow) => (
          <div className="flex justify-end gap-1">
            <Button size="sm" variant="ghost" onClick={() => openAdjust(row)} icon={<PackagePlus size={13} aria-hidden />} aria-label={`Adjust stock for ${row.name}`}>
              Adjust
            </Button>
            <Button size="sm" variant="ghost" onClick={() => openConfig(row)} icon={<Settings2 size={13} aria-hidden />} aria-label={`Configure ${row.name}`}>
              Rules
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setLedgerProduct(row)} icon={<History size={13} aria-hidden />} aria-label={`Movement history for ${row.name}`}>
              Ledger
            </Button>
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [currency],
  );

  return (
    <div className="space-y-4">
      {inventoryApi.error ? <ErrorBanner error={inventoryApi.error} /> : null}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <StatPill label="SKUs" value={formatNumber(summary?.total_skus ?? 0)} />
        <StatPill label="Stock value" value={summary?.inventory_value != null ? formatCurrency(summary.inventory_value, currency) : "—"} />
        <StatPill label="Stockouts" value={summary?.counts?.stockout ?? 0} tone="bad" />
        <StatPill label="High risk" value={summary?.counts?.high ?? 0} tone="warn" />
        <StatPill label="Overstocked" value={summary?.counts?.overstock ?? 0} tone="warn" />
        <StatPill label="Avg cover" value={summary?.avg_cover_days != null ? `${summary.avg_cover_days}d` : "—"} />
      </div>

      <Callout tone="info" title="How risk is calculated">
        {summary?.demand_source === "forecast"
          ? "Demand comes from the latest forecast run; reorder points, cover days and risk levels use that demand with each product's lead time and safety-stock settings."
          : "No forecast run exists yet, so demand uses trailing 28-day sales. Generate a forecast for lead-time aware risk levels."}{" "}
        {summary?.forecast_run_id ? `Forecast run #${summary.forecast_run_id}.` : ""}
      </Callout>

      <Card>
        <CardHeader
          title="Inventory"
          description="Stock on hand, reorder rules and current risk per product"
          icon={<Boxes size={15} aria-hidden />}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
                <TextInput
                  aria-label="Search inventory"
                  placeholder="Search product or SKU…"
                  className="w-44 pl-7 text-xs sm:w-60"
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setPage(1);
                  }}
                />
              </div>
              <Select
                aria-label="Sort inventory"
                className="w-36 text-xs"
                value={sortBy}
                onChange={(event) => setSortBy(event.target.value)}
              >
                <option value="name">Name</option>
                <option value="current_stock">Stock level</option>
                <option value="value">Stock value</option>
                <option value="lead_time_days">Lead time</option>
              </Select>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setSortDir(sortDir === "asc" ? "desc" : "asc")}
                aria-label={`Sort ${sortDir === "asc" ? "descending" : "ascending"}`}
              >
                {sortDir === "asc" ? "Asc ↑" : "Desc ↓"}
              </Button>
            </div>
          }
        />
        {inventoryApi.loading && !data ? (
          <LoadingBlock rows={6} />
        ) : (
          <>
            <DataTable
              rows={data?.items ?? []}
              columns={columns}
              rowKey={(row) => row.product_id}
              pageSize={12}
              emptyTitle="No inventory records"
              emptyDescription="Create products or import a sales file with an inventory column."
              caption="Inventory table"
            />
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-3 py-2 text-[11px] text-muted">
              <span>
                Page {data?.page ?? 1} of {data?.pages ?? 1} · {formatNumber(data?.total ?? 0)} products
              </span>
              <div className="flex gap-1.5">
                <Button size="sm" variant="secondary" disabled={(data?.page ?? 1) <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={(data?.page ?? 1) >= (data?.pages ?? 1)}
                  onClick={() => setPage((value) => value + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>

      {((data?.items ?? []).filter((row) => row.risk_level === "stockout" || row.risk_level === "high").length ?? 0) > 0 ? (
        <Callout tone="warning" title="Products at risk right now">
          <ul className="space-y-1">
            {(data?.items ?? [])
              .filter((row) => row.risk_level === "stockout" || row.risk_level === "high")
              .slice(0, 4)
              .map((row) => (
                <li key={row.product_id}>
                  <span className="font-medium text-ink">{row.name}</span> — {row.risk_reason}
                </li>
              ))}
          </ul>
        </Callout>
      ) : null}

      {/* -------------------------------------------------- adjust stock modal */}
      <Modal
        open={Boolean(adjustRow)}
        onClose={() => setAdjustRow(null)}
        title={`Adjust stock — ${adjustRow?.name ?? ""}`}
        description="Every change is written to the stock movement ledger with the reason and actor."
        footer={
          <>
            <Button variant="secondary" onClick={() => setAdjustRow(null)}>
              Cancel
            </Button>
            <Button onClick={submitAdjust} loading={busy}>
              Record adjustment
            </Button>
          </>
        }
      >
        {adjustRow ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <StatPill label="Current stock" value={formatNumber(adjustRow.current_stock)} />
              <StatPill label="After adjustment" value={formatNumber(adjustRow.current_stock + Number(adjustForm.quantity_delta || 0))} />
            </div>
            <Field
              label="Quantity change"
              htmlFor="adjust-delta"
              hint="Positive = received / found stock. Negative = damage, theft or correction."
              error={formError ?? undefined}
            >
              <TextInput
                id="adjust-delta"
                type="number"
                step="1"
                value={adjustForm.quantity_delta}
                onChange={(event) => setAdjustForm({ ...adjustForm, quantity_delta: Number(event.target.value) })}
              />
            </Field>
            <Field label="Reason (required)" htmlFor="adjust-reason">
              <TextInput
                id="adjust-reason"
                placeholder="e.g. Cycle count correction, delivery received"
                value={adjustForm.reason}
                onChange={(event) => setAdjustForm({ ...adjustForm, reason: event.target.value })}
              />
            </Field>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Recorded by" htmlFor="adjust-actor">
                <TextInput
                  id="adjust-actor"
                  value={adjustForm.actor}
                  onChange={(event) => setAdjustForm({ ...adjustForm, actor: event.target.value })}
                />
              </Field>
              <Field label="Reference (optional)" htmlFor="adjust-ref">
                <TextInput
                  id="adjust-ref"
                  placeholder="GRN / invoice number"
                  value={adjustForm.reference}
                  onChange={(event) => setAdjustForm({ ...adjustForm, reference: event.target.value })}
                />
              </Field>
            </div>
            {adjustRow.current_stock + Number(adjustForm.quantity_delta || 0) < 0 ? (
              <Callout tone="danger" title="This would make stock negative">
                The API rejects adjustments below zero. Record a correction against the original batch instead.
              </Callout>
            ) : null}
          </div>
        ) : null}
      </Modal>

      {/* ------------------------------------------------------ config modal */}
      <Modal
        open={Boolean(configRow)}
        onClose={() => setConfigRow(null)}
        title={`Reorder rules — ${configRow?.name ?? ""}`}
        description="These values drive reorder points, safety stock and suggested order quantities."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfigRow(null)}>
              Cancel
            </Button>
            <Button onClick={submitConfig} loading={busy}>
              Save rules
            </Button>
          </>
        }
      >
        {configRow ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {formError ? <div className="sm:col-span-2"><Callout tone="danger">{formError}</Callout></div> : null}
            <Field label="Current stock" htmlFor="cfg-stock">
              <TextInput
                id="cfg-stock"
                type="number"
                min={0}
                value={configForm.current_stock}
                onChange={(event) => setConfigForm({ ...configForm, current_stock: Number(event.target.value) })}
              />
            </Field>
            <Field label="Reorder threshold" htmlFor="cfg-threshold" hint="Simple manual trigger, independent of the forecast.">
              <TextInput
                id="cfg-threshold"
                type="number"
                min={0}
                value={configForm.reorder_threshold}
                onChange={(event) => setConfigForm({ ...configForm, reorder_threshold: Number(event.target.value) })}
              />
            </Field>
            <Field label="Supplier lead time (days)" htmlFor="cfg-lead">
              <TextInput
                id="cfg-lead"
                type="number"
                min={0}
                max={365}
                value={configForm.lead_time_days}
                onChange={(event) => setConfigForm({ ...configForm, lead_time_days: Number(event.target.value) })}
              />
            </Field>
            <Field label="Review period (days)" htmlFor="cfg-review">
              <TextInput
                id="cfg-review"
                type="number"
                min={1}
                max={180}
                value={configForm.review_period_days}
                onChange={(event) => setConfigForm({ ...configForm, review_period_days: Number(event.target.value) })}
              />
            </Field>
            <Field label="Safety stock (days)" htmlFor="cfg-safety">
              <TextInput
                id="cfg-safety"
                type="number"
                min={0}
                max={90}
                step="0.5"
                value={configForm.safety_stock_days}
                onChange={(event) => setConfigForm({ ...configForm, safety_stock_days: Number(event.target.value) })}
              />
            </Field>
            <Field label="Minimum order quantity" htmlFor="cfg-moq">
              <TextInput
                id="cfg-moq"
                type="number"
                min={1}
                value={configForm.min_order_qty}
                onChange={(event) => setConfigForm({ ...configForm, min_order_qty: Number(event.target.value) })}
              />
            </Field>
            <Field label="Pack size" htmlFor="cfg-pack" hint="Orders are rounded up to whole packs.">
              <TextInput
                id="cfg-pack"
                type="number"
                min={1}
                value={configForm.pack_size}
                onChange={(event) => setConfigForm({ ...configForm, pack_size: Number(event.target.value) })}
              />
            </Field>
          </div>
        ) : null}
      </Modal>

      {/* ------------------------------------------------------ ledger modal */}
      <Modal
        open={Boolean(ledgerProduct)}
        onClose={() => setLedgerProduct(null)}
        title={`Stock movements — ${ledgerProduct?.name ?? ""}`}
        description="Append-only ledger of every stock change with actor and reason"
        width="max-w-2xl"
      >
        {movementsApi.loading ? (
          <LoadingBlock rows={4} />
        ) : (movementsApi.data ?? []).length ? (
          <ul className="space-y-2">
            {(movementsApi.data as StockMovement[]).map((movement) => (
              <li key={movement.id} className="rounded-lg border border-line bg-elevated p-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span
                      className={
                        movement.quantity_delta >= 0
                          ? "rounded bg-positive/10 px-1.5 py-0.5 text-[11px] font-medium text-positive"
                          : "rounded bg-danger/10 px-1.5 py-0.5 text-[11px] font-medium text-danger"
                      }
                    >
                      {movement.quantity_delta > 0 ? "+" : ""}
                      {formatNumber(movement.quantity_delta)}
                    </span>
                    <StatusBadge status={movement.movement_type} />
                    <span className="text-[11px] text-muted">
                      {formatNumber(movement.previous_stock)} → {formatNumber(movement.new_stock)}
                    </span>
                  </div>
                  <span className="text-[10.5px] text-muted">{formatDateTime(movement.created_at)}</span>
                </div>
                <p className="mt-1 text-[11px] text-muted">
                  {movement.reason ?? "No reason recorded"} · by {movement.actor}
                  {movement.reference ? ` · ref ${movement.reference}` : ""}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            title="No movements yet"
            description="Stock adjustments, import snapshots and receipts will appear here."
            icon={<TriangleAlert size={16} aria-hidden />}
          />
        )}
      </Modal>

      <p className="text-center text-[10.5px] text-muted">
        <Badge tone="neutral">Audited</Badge> Every stock change is stored with previous/new levels, actor and reason — visible in
        Settings → Audit trail.
      </p>
    </div>
  );
}
