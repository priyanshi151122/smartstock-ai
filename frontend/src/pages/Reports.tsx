/** Reports & exports: generate CSV/XLSX/PDF from the current filters. */

import { useState } from "react";
import { ClipboardList, Download, FileSpreadsheet, FileText, FileType2, RefreshCw } from "lucide-react";
import { useApp } from "../context/AppContext";
import { endpoints, toApiError } from "../lib/api";
import { useApi } from "../lib/hooks";
import { formatDateTime, formatNumber } from "../lib/format";
import { DataTable } from "../components/DataTable";
import { ErrorBanner } from "../components/Banners";
import { Badge, Button, Callout, Card, CardHeader, Field, LoadingBlock, Select, TextInput } from "../components/ui";
import type { ReportFile } from "../lib/types";

const REPORT_OPTIONS = [
  { value: "sales_summary", label: "Sales summary", hint: "KPIs, daily sales, category and product totals" },
  { value: "product_performance", label: "Product performance", hint: "ABC classes, growth, margin and variability" },
  { value: "demand_forecast", label: "Demand forecast", hint: "Forecast values, metrics and run metadata" },
  { value: "inventory_risk", label: "Inventory risk", hint: "Stock, cover days and risk level per product" },
  { value: "reorder_recommendations", label: "Reorder recommendations", hint: "Quantities, costs and explanations" },
];

const FORMAT_OPTIONS = [
  { value: "xlsx", label: "Excel workbook (.xlsx)", icon: <FileSpreadsheet size={13} aria-hidden /> },
  { value: "csv", label: "CSV (.csv)", icon: <FileText size={13} aria-hidden /> },
  { value: "pdf", label: "PDF report (.pdf)", icon: <FileType2 size={13} aria-hidden /> },
];

export default function Reports() {
  const { filterParams, filters, pushToast } = useApp();
  const [reportType, setReportType] = useState("sales_summary");
  const [fileFormat, setFileFormat] = useState<"xlsx" | "csv" | "pdf">("xlsx");
  const [startDate, setStartDate] = useState(filterParams.start_date ?? "");
  const [endDate, setEndDate] = useState(filterParams.end_date ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const listApi = useApi(() => endpoints.reports({ limit: 30 }), []);

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await endpoints.generateReport({
        report_type: reportType,
        file_format: fileFormat,
        start_date: startDate || null,
        end_date: endDate || null,
        category: filters.category,
        product_id: filters.product_id,
        data_source: filters.data_source,
      });
      pushToast({
        tone: "success",
        title: `${result.filename} generated`,
        description: `${(result.size_bytes / 1024).toFixed(1)} KB · download link added to the list below.`,
      });
      listApi.reload();
    } catch (cause) {
      const apiError = toApiError(cause);
      setError(apiError.message);
      pushToast({ tone: "error", title: "Report failed", description: apiError.message });
    } finally {
      setBusy(false);
    }
  };

  const selected = REPORT_OPTIONS.find((option) => option.value === reportType);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Generate a report"
          description="Exports use exactly the filters below — the file matches what you see on screen."
          icon={<ClipboardList size={15} aria-hidden />}
          actions={<Badge tone="neutral">CSV · XLSX · PDF</Badge>}
        />
        <div className="card-pad grid grid-cols-1 gap-3 md:grid-cols-4">
          <Field label="Report type" htmlFor="report-type" hint={selected?.hint}>
            <Select id="report-type" value={reportType} onChange={(event) => setReportType(event.target.value)}>
              {REPORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Format" htmlFor="report-format">
            <Select id="report-format" value={fileFormat} onChange={(event) => setFileFormat(event.target.value as "xlsx" | "csv" | "pdf")}>
              {FORMAT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="From" htmlFor="report-start">
            <TextInput id="report-start" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          </Field>
          <Field label="To" htmlFor="report-end">
            <TextInput id="report-end" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </Field>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-3 sm:px-5">
          <p className="text-[11px] text-muted">
            Filters applied: {filters.category ?? "all categories"} · {filters.data_source ?? "all records"} ·{" "}
            {startDate || "start of history"} → {endDate || "latest record"}
          </p>
          <Button onClick={generate} loading={busy} icon={<Download size={13} aria-hidden />}>
            Generate {fileFormat.toUpperCase()}
          </Button>
        </div>
        {error ? (
          <div className="px-4 pb-3 sm:px-5">
            <Callout tone="danger" title="Could not generate the report">
              {error}
            </Callout>
          </div>
        ) : null}
        {reportType === "demand_forecast" ? (
          <div className="px-4 pb-3 sm:px-5">
            <Callout tone="info" title="Forecast reports need a completed run">
              The most recent forecast run is exported, including its evaluation metrics and limitations. Generate a forecast first if
              you have not run one yet.
            </Callout>
          </div>
        ) : null}
      </Card>

      {listApi.error ? <ErrorBanner error={listApi.error} /> : null}

      <Card>
        <CardHeader
          title="Generated files"
          description="Stored on the server; download links are scoped to this app"
          actions={
            <Button size="sm" variant="ghost" onClick={listApi.reload} icon={<RefreshCw size={13} aria-hidden />}>
              Refresh
            </Button>
          }
        />
        {listApi.loading && !listApi.data ? (
          <LoadingBlock rows={4} />
        ) : (
          <DataTable
            rows={listApi.data ?? []}
            columns={[
              {
                key: "filename",
                header: "File",
                value: (row: ReportFile) => row.filename,
                render: (row: ReportFile) => (
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="text-muted">
                      {row.file_format === "pdf" ? <FileType2 size={14} aria-hidden /> : row.file_format === "csv" ? <FileText size={14} aria-hidden /> : <FileSpreadsheet size={14} aria-hidden />}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-[11.5px] font-medium text-ink">{row.filename}</p>
                      <p className="text-[10.5px] text-muted capitalize">{row.report_type.replace(/_/g, " ")}</p>
                    </div>
                  </div>
                ),
                sortable: true,
              },
              { key: "format", header: "Format", value: (row: ReportFile) => row.file_format, render: (row: ReportFile) => row.file_format.toUpperCase(), sortable: true, align: "center" as const },
              {
                key: "size",
                header: "Size",
                align: "right" as const,
                value: (row: ReportFile) => row.size_bytes,
                render: (row: ReportFile) => `${(row.size_bytes / 1024).toFixed(1)} KB`,
                sortable: true,
              },
              {
                key: "created",
                header: "Generated",
                align: "right" as const,
                hideBelow: "sm" as const,
                value: (row: ReportFile) => row.created_at,
                render: (row: ReportFile) => <span className="text-[11px] text-muted">{formatDateTime(row.created_at)}</span>,
                sortable: true,
              },
              {
                key: "download",
                header: "",
                align: "right" as const,
                render: (row: ReportFile) => (
                  <a className="btn-secondary px-2.5 py-1 text-[11px]" href={row.download_url} download>
                    <Download size={12} aria-hidden /> Download
                  </a>
                ),
              },
            ]}
            rowKey={(row) => row.filename}
            pageSize={10}
            initialSort={{ key: "created", dir: "desc" }}
            emptyTitle="No reports generated yet"
            emptyDescription="Generate one above — files are stored server-side and can be re-downloaded later."
            caption="Generated reports"
          />
        )}
      </Card>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Card className="card-pad">
          <h3 className="text-sm font-semibold">Excel workbooks</h3>
          <p className="mt-1 text-[11px] text-muted">
            Multi-sheet workbooks with a report-info sheet, summary metrics and the full underlying table. Best for further analysis.
          </p>
        </Card>
        <Card className="card-pad">
          <h3 className="text-sm font-semibold">CSV</h3>
          <p className="mt-1 text-[11px] text-muted">
            Single-table export of the primary sheet. Cells are sanitised against spreadsheet formula injection.
          </p>
        </Card>
        <Card className="card-pad">
          <h3 className="text-sm font-semibold">PDF</h3>
          <p className="mt-1 text-[11px] text-muted">
            Printable summary with the reporting period, generation timestamp, a trend chart and the headline tables.
          </p>
        </Card>
      </div>

      <p className="text-center text-[10.5px] text-muted">
        {formatNumber(listApi.data?.length ?? 0)} files stored · exports reflect the filtered result set, never a cached template.
      </p>
    </div>
  );
}
