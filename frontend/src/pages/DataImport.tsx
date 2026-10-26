/** Data import: upload → map/validate → clean → commit, with a full audit trail. */

import { useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Download,
  FileSpreadsheet,
  FileText,
  Upload,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { endpoints, toApiError } from "../lib/api";
import { useApi } from "../lib/hooks";
import { formatDateTime, formatNumber } from "../lib/format";
import { DataTable } from "../components/DataTable";
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
  StatusBadge,
  Switch,
  cx,
} from "../components/ui";
import type { ImportBatch, ImportValidateResponse, ValidationIssue } from "../lib/types";

const FIELD_LABELS: Record<string, string> = {
  sku: "Product ID / SKU",
  product_name: "Product name",
  date: "Sale date",
  quantity: "Quantity sold",
  unit_price: "Unit price",
  revenue: "Revenue",
  category: "Category",
  store: "Store",
  supplier: "Supplier",
  inventory: "Current inventory",
  unit_cost: "Unit cost",
  order_id: "Order ID",
};

const STEP_LABELS = ["Upload", "Validate & map", "Import"];

export default function DataImport() {
  const { pushToast, refreshMeta, refreshSettings, settings } = useApp();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [report, setReport] = useState<ImportValidateResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<"actual" | "demo">("actual");
  const [cleaning, setCleaning] = useState<string[]>([]);
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [issuesOpen, setIssuesOpen] = useState(false);
  const [lastImport, setLastImport] = useState<{ imported_rows: number; products_created: number; rejected_rows: number; message: string; batch_id: number } | null>(null);

  const historyApi = useApi(() => endpoints.importHistory({ limit: 25 }), []);

  const step = lastImport ? 2 : report ? 1 : 0;
  const maxMb = settings?.max_upload_mb ?? 10;

  const upload = async (file: File) => {
    setUploadError(null);
    setLastImport(null);
    if (!/\.(csv|xlsx|xlsm)$/i.test(file.name)) {
      setUploadError("Only .csv, .xlsx or .xlsm files are accepted.");
      return;
    }
    if (file.size > maxMb * 1024 * 1024) {
      setUploadError(`File is ${(file.size / 1024 / 1024).toFixed(1)} MB which exceeds the ${maxMb} MB limit.`);
      return;
    }
    setUploading(true);
    try {
      const result = await endpoints.uploadSales(file, dataSource);
      setReport(result);
      setCleaning(result.cleaning_suggestions.filter((item) => item.default_applied).map((item) => item.code));
      historyApi.reload();
      if (!result.can_import) {
        setIssuesOpen(true);
      }
    } catch (error) {
      setUploadError(toApiError(error).message);
    } finally {
      setUploading(false);
    }
  };

  const commit = async () => {
    if (!report) return;
    setCommitting(true);
    try {
      const result = await endpoints.commitImport({
        batch_id: report.batch_id,
        apply_cleaning: cleaning,
        skip_duplicates: skipDuplicates,
        data_source: dataSource,
      });
      setLastImport(result);
      pushToast({ tone: "success", title: "Import complete", description: result.message });
      historyApi.reload();
      refreshMeta();
      refreshSettings();
    } catch (error) {
      pushToast({ tone: "error", title: "Import failed", description: toApiError(error).message });
    } finally {
      setCommitting(false);
    }
  };

  const reset = () => {
    setReport(null);
    setLastImport(null);
    setUploadError(null);
    setCleaning([]);
    if (fileInput.current) fileInput.current.value = "";
  };

  const issueColumns = useMemo(
    () => [
      { key: "row", header: "Row", align: "right" as const, value: (row: ValidationIssue) => row.row ?? 0, sortable: true, render: (row: ValidationIssue) => row.row ?? "—" },
      {
        key: "severity",
        header: "Severity",
        value: (row: ValidationIssue) => row.severity,
        sortable: true,
        render: (row: ValidationIssue) => (
          <Badge tone={row.severity === "error" ? "danger" : row.severity === "warning" ? "warning" : "neutral"}>
            {row.severity}
          </Badge>
        ),
      },
      { key: "code", header: "Code", value: (row: ValidationIssue) => row.code, render: (row: ValidationIssue) => <code className="text-[10.5px]">{row.code}</code>, sortable: true },
      { key: "message", header: "Message", value: (row: ValidationIssue) => row.message, render: (row: ValidationIssue) => <span className="text-[11px]">{row.message}</span> },
      {
        key: "suggestion",
        header: "Suggested fix",
        hideBelow: "lg" as const,
        value: (row: ValidationIssue) => row.suggestion ?? "",
        render: (row: ValidationIssue) => <span className="text-[11px] text-muted">{row.suggestion ?? "—"}</span>,
      },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Import sales data"
          description="CSV or Excel exports are validated row by row before anything is written to the database."
          icon={<Database size={15} aria-hidden />}
          actions={
            <div className="flex gap-1.5">
              <a className="btn-secondary px-2.5 py-1.5 text-xs" href={endpoints.templateUrl("csv")} download>
                <Download size={13} aria-hidden /> CSV template
              </a>
              <a className="btn-secondary px-2.5 py-1.5 text-xs" href={endpoints.templateUrl("xlsx")} download>
                <Download size={13} aria-hidden /> XLSX template
              </a>
            </div>
          }
        />
        <div className="card-pad">
          <ol className="mb-4 flex flex-wrap items-center gap-2 text-[11px]">
            {STEP_LABELS.map((label, index) => (
              <li key={label} className="flex items-center gap-2">
                <span
                  className={cx(
                    "grid h-5 w-5 place-items-center rounded-full border text-[10px] font-semibold",
                    step === index
                      ? "border-accent bg-accent text-white dark:text-slate-950"
                      : step > index
                        ? "border-positive bg-positive/15 text-positive"
                        : "border-line bg-elevated text-muted",
                  )}
                >
                  {step > index ? <CheckCircle2 size={11} aria-hidden /> : index + 1}
                </span>
                <span className={step === index ? "font-medium text-ink" : "text-muted"}>{label}</span>
                {index < STEP_LABELS.length - 1 ? <span className="text-muted">→</span> : null}
              </li>
            ))}
          </ol>

          <div
            className={cx(
              "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition",
              dragging ? "border-accent bg-accent/5" : "border-line bg-elevated/50",
            )}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              const file = event.dataTransfer.files?.[0];
              if (file) void upload(file);
            }}
          >
            <span className="grid h-11 w-11 place-items-center rounded-full border border-line bg-surface text-accent">
              <Upload size={18} aria-hidden />
            </span>
            <p className="text-sm font-medium">Drop a sales file here, or choose one</p>
            <p className="max-w-md text-[11px] text-muted">
              CSV, XLSX or XLSM up to {maxMb} MB. Required fields: product identifier, sale date and quantity. Optional: price,
              category, store, supplier, inventory, unit cost and order id.
            </p>
            <input
              ref={fileInput}
              type="file"
              accept=".csv,.xlsx,.xlsm"
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void upload(file);
              }}
            />
            <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
              <Button size="sm" onClick={() => fileInput.current?.click()} loading={uploading} icon={<FileSpreadsheet size={13} aria-hidden />}>
                Choose file
              </Button>
              <label className="flex items-center gap-1.5 text-[11px] text-muted">
                Mark as
                <Select
                  aria-label="Data source label"
                  className="w-36 py-1 text-[11px]"
                  value={dataSource}
                  onChange={(event) => setDataSource(event.target.value as "actual" | "demo")}
                >
                  <option value="actual">Real shop records</option>
                  <option value="demo">Demo / test data</option>
                </Select>
              </label>
            </div>
          </div>

          {uploadError ? (
            <div className="mt-3">
              <Callout tone="danger" title="Upload rejected">
                {uploadError}
              </Callout>
            </div>
          ) : null}
          {uploading ? (
            <div className="mt-3">
              <LoadingBlock label="Uploading and validating" rows={3} />
            </div>
          ) : null}
        </div>
      </Card>

      {report ? (
        <Card>
          <CardHeader
            title="Validation results"
            description={`${report.filename} · ${report.file_type.toUpperCase()} · ${(report.file_size_bytes / 1024).toFixed(1)} KB`}
            icon={<FileText size={15} aria-hidden />}
            actions={
              <div className="flex flex-wrap gap-1.5">
                <a className="btn-secondary px-2.5 py-1.5 text-xs" href={endpoints.validationReportUrl(report.batch_id)} download>
                  <Download size={13} aria-hidden /> Validation report
                </a>
                {!lastImport ? (
                  <Button size="sm" variant="ghost" onClick={reset}>
                    Start over
                  </Button>
                ) : null}
              </div>
            }
          />

          <div className="grid grid-cols-2 gap-2 px-4 pt-3 sm:grid-cols-4 sm:px-5">
            <StatPill label="Rows in file" value={formatNumber(report.total_rows)} />
            <StatPill label="Valid" value={formatNumber(report.valid_rows)} tone="good" />
            <StatPill label="Invalid" value={formatNumber(report.invalid_rows)} tone={report.invalid_rows ? "bad" : "neutral"} />
            <StatPill label="Duplicates" value={formatNumber(report.duplicate_rows)} tone={report.duplicate_rows ? "warn" : "neutral"} />
          </div>

          {report.required_fields_missing.length ? (
            <div className="px-4 pt-3 sm:px-5">
              <Callout tone="danger" title="Required columns are missing">
                {report.required_fields_missing.map((field) => FIELD_LABELS[field] ?? field).join(", ")} — map them manually below or
                fix the file header. Nothing can be imported until every required field is mapped.
              </Callout>
            </div>
          ) : null}

          {report.warnings.length ? (
            <div className="px-4 pt-3 sm:px-5">
              <Callout tone="warning" title="Warnings">
                <ul className="list-disc space-y-0.5 pl-3">
                  {report.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </Callout>
            </div>
          ) : null}

          <div className="card-pad grid grid-cols-1 gap-3 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Column mapping</h3>
              <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1 scroll-thin">
                {Object.entries(FIELD_LABELS).map(([field, label]) => (
                  <div key={field} className="flex items-center justify-between gap-2 rounded-lg border border-line bg-elevated px-2 py-1.5">
                    <span className="text-[11px] text-muted">{label}</span>
                    <span className={cx("text-[11px] font-medium", report.mapping[field] ? "text-ink" : "text-muted/70")}>
                      {report.mapping[field] ?? "not mapped"}
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[10.5px] text-muted">
                Detected columns: {report.detected_columns.join(", ")}
              </p>
            </div>

            <div className="flex min-h-0 flex-col">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Cleaning rules</h3>
              <div className="space-y-1.5">
                {report.cleaning_suggestions.map((suggestion) => (
                  <label
                    key={suggestion.code}
                    className="flex cursor-pointer items-start gap-2 rounded-lg border border-line bg-elevated px-2 py-1.5"
                  >
                    <input
                      type="checkbox"
                      className="mt-0.5 h-3.5 w-3.5 accent-[rgb(var(--c-accent))]"
                      checked={cleaning.includes(suggestion.code)}
                      onChange={(event) =>
                        setCleaning((current) =>
                          event.target.checked ? [...current, suggestion.code] : current.filter((code) => code !== suggestion.code),
                        )
                      }
                    />
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-ink">
                        {suggestion.label}
                        {suggestion.affected_rows > 0 ? <Badge tone="accent">{suggestion.affected_rows} rows</Badge> : null}
                      </span>
                      <span className="block text-[10.5px] text-muted">{suggestion.description}</span>
                    </span>
                  </label>
                ))}
              </div>
              <div className="mt-2 border-t border-line pt-2">
                <Switch
                  label="Skip duplicate rows"
                  description="Rows matching an existing (product, date, quantity, price) record are not imported."
                  checked={skipDuplicates}
                  onChange={setSkipDuplicates}
                />
              </div>
            </div>
          </div>

          {report.preview_rows.length ? (
            <div className="border-t border-line">
              <p className="px-4 pt-3 text-xs font-semibold uppercase tracking-wide text-muted sm:px-5">Preview (first rows)</p>
              <div className="overflow-x-auto scroll-thin px-4 pb-2 sm:px-5">
                <table className="table-base mt-1 text-[11px]">
                  <thead>
                    <tr>
                      {Object.keys(report.preview_rows[0]).map((key) => (
                        <th key={key} scope="col">
                          {key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {report.preview_rows.map((row, index) => (
                      <tr key={index}>
                        {Object.keys(report.preview_rows[0]).map((key) => (
                          <td key={key} className="whitespace-nowrap">
                            {row[key] === null || row[key] === undefined || row[key] === "" ? (
                              <span className="text-muted/60">—</span>
                            ) : (
                              String(row[key])
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-3 sm:px-5">
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
              <Button size="sm" variant="secondary" onClick={() => setIssuesOpen(true)} icon={<AlertTriangle size={13} aria-hidden />}>
                View {report.issues.length} validation issues
              </Button>
              <span>
                {Object.entries(report.issue_counts)
                  .slice(0, 3)
                  .map(([code, count]) => `${code} ×${count}`)
                  .join(" · ")}
              </span>
            </div>
            <Button
              onClick={commit}
              loading={committing}
              disabled={!report.can_import || Boolean(lastImport)}
              icon={<CheckCircle2 size={13} aria-hidden />}
            >
              Import {formatNumber(report.valid_rows)} valid rows
            </Button>
          </div>

          {lastImport ? (
            <div className="border-t border-line px-4 py-3 sm:px-5">
              <Callout tone="success" title="Import completed">
                {lastImport.message} Batch #{lastImport.batch_id}. The dashboard and forecasts now use these records.
              </Callout>
            </div>
          ) : null}
        </Card>
      ) : null}

      <Card>
        <CardHeader title="Import history" description="Every upload is stored with its validation and cleaning outcome" icon={<FileSpreadsheet size={15} aria-hidden />} />
        <DataTable
          rows={historyApi.data ?? []}
          columns={[
            { key: "id", header: "Batch", value: (row: ImportBatch) => row.id, render: (row: ImportBatch) => `#${row.id}`, sortable: true, align: "right" as const },
            {
              key: "filename",
              header: "File",
              value: (row: ImportBatch) => row.filename,
              render: (row: ImportBatch) => (
                <div className="min-w-0">
                  <p className="truncate text-[11.5px] font-medium text-ink">{row.filename}</p>
                  <p className="text-[10.5px] text-muted">
                    {row.file_type.toUpperCase()} · {row.data_source === "demo" ? "demo data" : "real records"} · {formatDateTime(row.created_at)}
                  </p>
                </div>
              ),
            },
            {
              key: "status",
              header: "Status",
              value: (row: ImportBatch) => row.status,
              render: (row: ImportBatch) => <StatusBadge status={row.status} />,
              sortable: true,
              align: "center" as const,
            },
            { key: "total", header: "Rows", align: "right" as const, value: (row: ImportBatch) => row.total_rows, render: (row: ImportBatch) => formatNumber(row.total_rows), sortable: true },
            { key: "imported", header: "Imported", align: "right" as const, value: (row: ImportBatch) => row.imported_rows, render: (row: ImportBatch) => formatNumber(row.imported_rows), sortable: true },
            {
              key: "invalid",
              header: "Rejected",
              align: "right" as const,
              hideBelow: "sm" as const,
              value: (row: ImportBatch) => row.invalid_rows,
              render: (row: ImportBatch) => (row.invalid_rows ? <span className="text-danger">{formatNumber(row.invalid_rows)}</span> : "0"),
              sortable: true,
            },
            {
              key: "report",
              header: "Report",
              align: "right" as const,
              render: (row: ImportBatch) => (
                <a className="btn-ghost px-2 py-1 text-[11px]" href={endpoints.validationReportUrl(row.id)} download>
                  <Download size={12} aria-hidden /> XLSX
                </a>
              ),
            },
          ]}
          rowKey={(row) => row.id}
          pageSize={8}
          initialSort={{ key: "id", dir: "desc" }}
          emptyTitle="No imports yet"
          emptyDescription="Upload a CSV or Excel sales export to get started."
          caption="Import history"
        />
      </Card>

      <Modal open={issuesOpen} onClose={() => setIssuesOpen(false)} title="Validation issues" description="Every problem is tied to a row number in your file" width="max-w-3xl">
        {report ? (
          report.issues.length ? (
            <DataTable
              rows={report.issues}
              columns={issueColumns}
              rowKey={(row) => `${row.row ?? "file"}-${row.code}-${row.column ?? ""}`}
              pageSize={10}
              emptyTitle="No issues"
            />
          ) : (
            <EmptyState title="No validation issues" description="Every row passed the checks." icon={<CheckCircle2 size={16} aria-hidden />} />
          )
        ) : null}
      </Modal>

      <Callout tone="info" title="Nothing is imported silently">
        Invalid rows are never discarded without a record; they are counted, listed with row numbers and included in the downloadable
        validation report. Duplicate detection compares product, date, quantity and price against every stored row.
      </Callout>
    </div>
  );
}
