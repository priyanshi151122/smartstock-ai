/** Reorder recommendations: explainable quantities, approvals creating drafts only. */

import { useMemo, useState } from "react";
import { CheckCircle2, Download, FileText, RefreshCw, Search, ShoppingCart, XCircle } from "lucide-react";
import { useApp } from "../context/AppContext";
import { endpoints, toApiError } from "../lib/api";
import { useApi, useDebounced } from "../lib/hooks";
import { formatCurrency, formatDateTime, formatNumber } from "../lib/format";
import { DataTable } from "../components/DataTable";
import { SectionTitle } from "../components/FilterBar";
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
  cx,
} from "../components/ui";
import type { Recommendation } from "../lib/types";

export default function ReorderRecommendations() {
  const { filters, currency, pushToast, refreshMeta } = useApp();
  const [status, setStatus] = useState<"pending" | "approved" | "dismissed" | "">("pending");
  const [risk, setRisk] = useState("");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("risk_priority");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const debounced = useDebounced(search);

  const [detail, setDetail] = useState<Recommendation | null>(null);
  const [decision, setDecision] = useState<{ row: Recommendation; status: "approved" | "dismissed" } | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const recoApi = useApi(
    () =>
      endpoints.recommendations({
        status: status || null,
        risk_level: risk || null,
        search: debounced || null,
        category: filters.category,
        sort_by: sortBy,
        sort_dir: sortDir,
        page_size: 100,
      }),
    [status, risk, debounced, filters.category, sortBy, sortDir],
  );

  const data = recoApi.data;

  const regenerate = async () => {
    setGenerating(true);
    try {
      const result = await endpoints.generateRecommendations({
        horizon_days: null,
        category: filters.category,
      });
      pushToast({
        tone: "success",
        title: `${result.created} recommendations refreshed`,
        description: result.forecast_used
          ? `Using forecast run #${result.run_id} · ${result.horizon_days}-day horizon.`
          : "No forecast available — trailing demand was used instead.",
      });
      recoApi.reload();
      refreshMeta();
    } catch (error) {
      pushToast({ tone: "error", title: "Could not generate recommendations", description: toApiError(error).message });
    } finally {
      setGenerating(false);
    }
  };

  const exportReport = async (format: "csv" | "xlsx") => {
    try {
      await endpoints.generateReport({
        report_type: "reorder_recommendations",
        file_format: format,
        category: filters.category,
      });
      pushToast({ tone: "success", title: "Export ready", description: "Download it from Reports & Exports." });
    } catch (error) {
      pushToast({ tone: "error", title: toApiError(error).message });
    }
  };

  const submitDecision = async () => {
    if (!decision) return;
    setBusy(true);
    setFormError(null);
    try {
      const updated = await endpoints.decideRecommendation(decision.row.id, {
        status: decision.status,
        note: note || undefined,
        actor: "store-manager",
      });
      pushToast({
        tone: "success",
        title: decision.status === "approved" ? "Purchase draft created" : "Recommendation dismissed",
        description:
          decision.status === "approved"
            ? `${updated.order_draft_ref} for ${formatNumber(updated.suggested_quantity)} × ${updated.product_name}. No order has been sent to the supplier.`
            : `${updated.product_name} dismissed from the current draft.`,
      });
      setDecision(null);
      setNote("");
      recoApi.reload();
    } catch (error) {
      setFormError(toApiError(error).message);
    } finally {
      setBusy(false);
    }
  };

  const columns = useMemo(
    () => [
      {
        key: "product",
        header: "Product",
        sortable: true,
        value: (row: Recommendation) => row.product_name,
        render: (row: Recommendation) => (
          <button type="button" className="min-w-0 text-left" onClick={() => setDetail(row)}>
            <p className="truncate font-medium text-ink underline decoration-dotted decoration-transparent hover:decoration-line">
              {row.product_name}
            </p>
            <p className="text-[10.5px] text-muted">
              {row.sku} · {row.category ?? "—"}
            </p>
          </button>
        ),
      },
      {
        key: "risk",
        header: "Risk",
        sortable: true,
        value: (row: Recommendation) => row.risk_level,
        render: (row: Recommendation) => <RiskBadge level={row.risk_level} />,
      },
      {
        key: "current_stock",
        header: "Stock",
        align: "right" as const,
        sortable: true,
        value: (row: Recommendation) => row.current_stock,
        render: (row: Recommendation) => (
          <span className={row.current_stock <= 0 ? "font-medium text-danger" : ""}>{formatNumber(row.current_stock)}</span>
        ),
      },
      {
        key: "forecast_demand",
        header: "Forecast demand",
        align: "right" as const,
        hideBelow: "lg" as const,
        sortable: true,
        value: (row: Recommendation) => row.forecast_demand,
        render: (row: Recommendation) => (
          <span title={`${row.avg_daily_demand.toFixed(2)} units/day over ${row.forecast_horizon_days} days`}>
            {formatNumber(row.forecast_demand, 0)}
          </span>
        ),
      },
      {
        key: "safety_stock",
        header: "Safety",
        align: "right" as const,
        hideBelow: "2xl" as const,
        sortable: true,
        value: (row: Recommendation) => row.safety_stock,
        render: (row: Recommendation) => formatNumber(row.safety_stock, 1),
      },
      {
        key: "reorder_point",
        header: "Reorder pt.",
        align: "right" as const,
        hideBelow: "lg" as const,
        sortable: true,
        value: (row: Recommendation) => row.reorder_point,
        render: (row: Recommendation) => formatNumber(row.reorder_point, 1),
      },
      {
        key: "suggested_quantity",
        header: "Order qty",
        align: "right" as const,
        sortable: true,
        value: (row: Recommendation) => row.suggested_quantity,
        render: (row: Recommendation) => (
          <span className="font-medium text-ink">{formatNumber(row.suggested_quantity)}</span>
        ),
      },
      {
        key: "lead_time_days",
        header: "Lead",
        align: "right" as const,
        hideBelow: "2xl" as const,
        sortable: true,
        value: (row: Recommendation) => row.lead_time_days,
        render: (row: Recommendation) => `${row.lead_time_days}d`,
      },
      {
        key: "estimated_cost",
        header: "Est. cost",
        align: "right" as const,
        hideBelow: "xl" as const,
        sortable: true,
        value: (row: Recommendation) => row.estimated_cost ?? -1,
        render: (row: Recommendation) =>
          row.estimated_cost === null ? <span className="text-[10.5px] text-muted">no cost</span> : formatCurrency(row.estimated_cost, currency),
      },
      {
        key: "status",
        header: "Status",
        align: "center" as const,
        hideBelow: "lg" as const,
        render: (row: Recommendation) => (
          <div className="flex flex-col items-center gap-1">
            <StatusBadge status={row.status} />
            {row.order_draft_ref ? <span className="text-[9.5px] text-muted">{row.order_draft_ref}</span> : null}
          </div>
        ),
      },
      {
        key: "actions",
        header: "Decide",
        align: "right" as const,
        render: (row: Recommendation) =>
          row.status === "pending" ? (
            <div className="flex justify-end gap-0.5">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setDecision({ row, status: "approved" });
                  setNote("");
                  setFormError(null);
                }}
                icon={<CheckCircle2 size={13} aria-hidden />}
                aria-label={`Approve ${row.product_name}`}
              >
                Approve
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setDecision({ row, status: "dismissed" });
                  setNote("");
                  setFormError(null);
                }}
                icon={<XCircle size={13} aria-hidden />}
                aria-label={`Dismiss ${row.product_name}`}
              >
                Dismiss
              </Button>
            </div>
          ) : (
            <span className="text-[10.5px] text-muted">{row.decided_at ? formatDateTime(row.decided_at) : "—"}</span>
          ),
      },
    ],
    [currency],
  );

  const pending = data?.counts?.pending ?? 0;

  return (
    <div className="space-y-4">
      {recoApi.error ? <ErrorBanner error={recoApi.error} /> : null}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatPill label="Pending" value={formatNumber(pending)} tone={pending > 0 ? "warn" : "good"} />
        <StatPill label="Approved" value={formatNumber(data?.counts?.approved ?? 0)} tone="good" />
        <StatPill label="Dismissed" value={formatNumber(data?.counts?.dismissed ?? 0)} />
        <StatPill label="Pending spend" value={formatCurrency(data?.pending_cost ?? 0, currency)} />
      </div>

      <Callout tone="info" title="Approving creates a purchase draft — nothing is ordered automatically">
        The app never contacts a supplier. An approval stores a draft reference (e.g. PO-DRAFT-00042), the quantity and an audit
        entry so a buyer can place the real order outside the system.
      </Callout>

      <Card>
        <CardHeader
          title="Reorder recommendations"
          description={`${formatNumber(data?.total ?? 0)} rows · quantities rounded to pack size and minimum order rules`}
          icon={<ShoppingCart size={15} aria-hidden />}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="secondary" onClick={regenerate} loading={generating} icon={<RefreshCw size={13} aria-hidden />}>
                Rebuild from forecast
              </Button>
              <Button size="sm" variant="ghost" onClick={() => exportReport("xlsx")} icon={<Download size={13} aria-hidden />}>
                XLSX
              </Button>
              <Button size="sm" variant="ghost" onClick={() => exportReport("csv")} icon={<Download size={13} aria-hidden />}>
                CSV
              </Button>
            </div>
          }
        />

        <div className="flex flex-wrap items-end gap-2 border-b border-line px-4 py-2.5 sm:px-5">
          <div className="relative">
            <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
            <TextInput
              aria-label="Search recommendations"
              placeholder="Search product…"
              className="w-44 pl-7 text-xs"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <Select aria-label="Filter by status" className="w-32 text-xs" value={status} onChange={(event) => setStatus(event.target.value as typeof status)}>
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="dismissed">Dismissed</option>
          </Select>
          <Select aria-label="Filter by risk" className="w-32 text-xs" value={risk} onChange={(event) => setRisk(event.target.value)}>
            <option value="">All risks</option>
            <option value="stockout">Stockout</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Healthy</option>
            <option value="overstock">Overstock</option>
          </Select>
          <Select aria-label="Sort recommendations" className="w-40 text-xs" value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
            <option value="risk_priority">Risk priority</option>
            <option value="suggested_quantity">Order quantity</option>
            <option value="estimated_cost">Estimated cost</option>
            <option value="coverage_days">Days of cover</option>
            <option value="product_name">Product name</option>
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

        {recoApi.loading && !data ? (
          <LoadingBlock rows={6} />
        ) : (data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title="No recommendations in this view"
            description="Rebuild from forecast to recalculate reorder points for every product, or clear the filters."
            icon={<ShoppingCart size={18} aria-hidden />}
            action={
              <Button size="sm" onClick={regenerate} loading={generating} icon={<RefreshCw size={13} aria-hidden />}>
                Rebuild recommendations
              </Button>
            }
          />
        ) : (
          <DataTable
            rows={data?.items ?? []}
            columns={columns}
            rowKey={(row) => row.id}
            pageSize={12}
            initialSort={{ key: "risk", dir: "asc" }}
            emptyTitle="Nothing to show"
            caption="Reorder recommendations table"
          />
        )}
      </Card>

      <SectionTitle
        title="How the quantity is calculated"
        subtitle="Average daily demand = forecast demand ÷ horizon · Reorder point = avg daily demand × lead time + safety stock · Suggested quantity = max(0, target − current stock), rounded up to pack size and minimum order quantity."
      />

      {/* ------------------------------------------------------ detail modal */}
      <Modal
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        title={detail?.product_name ?? ""}
        description={detail ? `${detail.sku} · ${detail.category ?? "—"} · ${detail.supplier_name ?? "no supplier"}` : ""}
        width="max-w-2xl"
      >
        {detail ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <StatPill label="Current stock" value={formatNumber(detail.current_stock)} />
              <StatPill label="Forecast demand" value={`${formatNumber(detail.forecast_demand)} / ${detail.forecast_horizon_days}d`} />
              <StatPill label="Avg daily demand" value={detail.avg_daily_demand.toFixed(2)} />
              <StatPill label="Safety stock" value={formatNumber(detail.safety_stock, 1)} />
              <StatPill label="Reorder point" value={formatNumber(detail.reorder_point, 1)} />
              <StatPill label="Target stock" value={formatNumber(detail.target_stock, 1)} />
              <StatPill label="Suggested qty" value={formatNumber(detail.suggested_quantity)} tone="good" />
              <StatPill label="Est. cost" value={detail.estimated_cost !== null ? formatCurrency(detail.estimated_cost, currency) : "—"} />
              <StatPill label="Days of cover" value={detail.coverage_days !== null ? `${detail.coverage_days.toFixed(1)}d` : "—"} />
            </div>
            <div className="rounded-lg border border-line bg-elevated p-3 text-[11.5px] leading-relaxed text-muted">
              <p className="mb-1 flex items-center gap-1 font-medium text-ink">
                <FileText size={12} aria-hidden /> Explanation
              </p>
              {detail.explanation}
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
              <StatPill label="Lead time" value={`${detail.lead_time_days}d`} />
              <StatPill label="Min order" value={formatNumber(detail.min_order_qty)} />
              <StatPill label="Pack size" value={formatNumber(detail.pack_size)} />
              <StatPill label="Demand source" value={detail.demand_source} />
            </div>
            {detail.status !== "pending" ? (
              <Callout tone={detail.status === "approved" ? "success" : "info"} title={`Decision: ${detail.status}`}>
                {detail.decided_by ?? "—"} on {formatDateTime(detail.decided_at)}
                {detail.decision_note ? ` — “${detail.decision_note}”` : ""}
                {detail.order_draft_ref ? ` · Draft ${detail.order_draft_ref}` : ""}
              </Callout>
            ) : null}
          </div>
        ) : null}
      </Modal>

      {/* ---------------------------------------------------- decision modal */}
      <Modal
        open={Boolean(decision)}
        onClose={() => setDecision(null)}
        title={decision?.status === "approved" ? "Approve purchase draft" : "Dismiss recommendation"}
        description={decision ? `${decision.row.product_name} · ${formatNumber(decision.row.suggested_quantity)} units` : ""}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDecision(null)}>
              Cancel
            </Button>
            <Button onClick={submitDecision} loading={busy} variant={decision?.status === "approved" ? "primary" : "danger"}>
              {decision?.status === "approved" ? "Create draft" : "Dismiss"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {formError ? <Callout tone="danger">{formError}</Callout> : null}
          {decision?.status === "approved" ? (
            <Callout tone="info" title="What happens next">
              A draft purchase order reference is stored with the quantity, supplier and estimated cost, plus an audit record.
              Nothing is transmitted to the supplier — place the actual order through your normal process.
            </Callout>
          ) : (
            <Callout tone="warning" title="Dismissing hides the recommendation">
              The product stays in inventory; you can rebuild recommendations later. Dismissals are kept for audit.
            </Callout>
          )}
          <Field label="Note (optional)" htmlFor="decision-note" hint="Why are you approving or dismissing this?">
            <TextInput
              id="decision-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder={decision?.status === "approved" ? "e.g. Combine with weekly supplier run" : "e.g. Switching supplier next month"}
            />
          </Field>
          <div className={cx("grid grid-cols-2 gap-2 text-[11px]", decision?.status !== "approved" && "opacity-60")}>
            <StatPill label="Quantity" value={formatNumber(decision?.row.suggested_quantity ?? 0)} />
            <StatPill
              label="Estimated cost"
              value={decision?.row.estimated_cost != null ? formatCurrency(decision.row.estimated_cost, currency) : "—"}
            />
          </div>
          <Badge tone="neutral">Actor recorded: store-manager</Badge>
        </div>
      </Modal>
    </div>
  );
}
