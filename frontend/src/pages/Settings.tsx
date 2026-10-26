/** Settings: store identity, currency, forecasting defaults, demo data, audit trail. */

import { useEffect, useState } from "react";
import { Database, History, Info, Save, ShieldCheck, Trash2 } from "lucide-react";
import { useApp } from "../context/AppContext";
import { endpoints, toApiError } from "../lib/api";
import { useApi } from "../lib/hooks";
import { formatDateTime, formatNumber } from "../lib/format";
import { DataTable } from "../components/DataTable";
import { ErrorBanner } from "../components/Banners";
import {
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  Field,
  LoadingBlock,
  Modal,
  Select,
  StatPill,
  Switch,
  TextInput,
} from "../components/ui";

export default function Settings() {
  const { settings, meta, refreshMeta, refreshSettings, pushToast, theme, setTheme } = useApp();
  const [form, setForm] = useState({
    store_name: "",
    currency: "INR",
    currency_symbol: "\u20b9",
    currency_locale: "en-IN",
    default_horizon_days: 14,
    service_level_z: 1.65,
    default_theme: "dark" as "dark" | "light",
  });
  const [saving, setSaving] = useState(false);
  const [busyDemo, setBusyDemo] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  const auditApi = useApi(() => endpoints.auditLogs({ limit: 40 }), []);
  const healthApi = useApi(() => endpoints.health(), []);

  useEffect(() => {
    if (!settings) return;
    setForm({
      store_name: settings.store_name,
      currency: settings.currency,
      currency_symbol: settings.currency_symbol,
      currency_locale: settings.currency_locale,
      default_horizon_days: settings.default_horizon_days,
      service_level_z: settings.service_level_z,
      default_theme: settings.default_theme,
    });
  }, [settings]);

  const save = async () => {
    setSaving(true);
    try {
      await endpoints.updateSettings(form);
      refreshSettings();
      refreshMeta();
      pushToast({ tone: "success", title: "Settings saved", description: "Currency and defaults apply across the app." });
    } catch (error) {
      pushToast({ tone: "error", title: toApiError(error).message });
    } finally {
      setSaving(false);
    }
  };

  const loadDemo = async () => {
    setBusyDemo(true);
    try {
      const result = await endpoints.loadDemo();
      pushToast({
        tone: "success",
        title: result.already_loaded ? "Demo data already loaded" : "Demo dataset loaded",
        description: result.already_loaded ? undefined : `${formatNumber(result.inserted_rows)} rows · ${result.products} products (labelled demo).`,
      });
      refreshMeta();
      refreshSettings();
    } catch (error) {
      pushToast({ tone: "error", title: toApiError(error).message });
    } finally {
      setBusyDemo(false);
    }
  };

  const clearDemo = async () => {
    setBusyDemo(true);
    try {
      const result = await endpoints.clearDemo();
      pushToast({ tone: "success", title: "Demo data removed", description: `${formatNumber(result.removed_rows)} rows deleted. Real records untouched.` });
      setConfirmClear(false);
      refreshMeta();
      refreshSettings();
    } catch (error) {
      pushToast({ tone: "error", title: toApiError(error).message });
    } finally {
      setBusyDemo(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <StatPill label="Products" value={formatNumber(settings?.products ?? 0)} />
        <StatPill label="Real rows" value={formatNumber(settings?.actual_rows ?? 0)} tone="good" />
        <StatPill label="Demo rows" value={formatNumber(settings?.demo_rows ?? 0)} tone={settings?.demo_rows ? "warn" : "neutral"} />
        <StatPill label="Database" value={settings?.database_dialect ?? "—"} />
        <StatPill label="Version" value={settings?.app_version ?? "—"} />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Store & display preferences"
            description="Currency formatting and forecasting defaults used across the dashboards"
            icon={<Info size={15} aria-hidden />}
            actions={
              <Button size="sm" onClick={save} loading={saving} icon={<Save size={13} aria-hidden />}>
                Save changes
              </Button>
            }
          />
          <div className="card-pad grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Store name" htmlFor="set-store">
              <TextInput id="set-store" value={form.store_name} onChange={(event) => setForm({ ...form, store_name: event.target.value })} />
            </Field>
            <Field label="Currency symbol" htmlFor="set-symbol" hint="Displayed on every monetary value.">
              <TextInput id="set-symbol" value={form.currency_symbol} maxLength={4} onChange={(event) => setForm({ ...form, currency_symbol: event.target.value })} />
            </Field>
            <Field label="Currency code" htmlFor="set-currency" hint="ISO-4217, e.g. INR, USD, EUR.">
              <TextInput
                id="set-currency"
                value={form.currency}
                maxLength={3}
                onChange={(event) => setForm({ ...form, currency: event.target.value.toUpperCase() })}
              />
            </Field>
            <Field label="Number locale" htmlFor="set-locale" hint="Controls digit grouping, e.g. en-IN.">
              <TextInput id="set-locale" value={form.currency_locale} onChange={(event) => setForm({ ...form, currency_locale: event.target.value })} />
            </Field>
            <Field label="Default forecast horizon" htmlFor="set-horizon">
              <Select
                id="set-horizon"
                value={form.default_horizon_days}
                onChange={(event) => setForm({ ...form, default_horizon_days: Number(event.target.value) })}
              >
                <option value={7}>7 days</option>
                <option value={14}>14 days</option>
                <option value={30}>30 days</option>
              </Select>
            </Field>
            <Field label="Service level z-score" htmlFor="set-z" hint="1.65 ≈ 95% cycle service level; used in safety stock.">
              <TextInput
                id="set-z"
                type="number"
                step="0.05"
                min={0}
                max={4}
                value={form.service_level_z}
                onChange={(event) => setForm({ ...form, service_level_z: Number(event.target.value) })}
              />
            </Field>
            <div className="sm:col-span-2 space-y-3 rounded-lg border border-line bg-elevated p-3">
              <Switch
                label="Dark theme by default"
                description="Saved with the setting; you can still toggle the theme from the header."
                checked={form.default_theme === "dark"}
                onChange={(checked) => {
                  const next = checked ? "dark" : "light";
                  setForm({ ...form, default_theme: next });
                  setTheme(next);
                }}
              />
              <p className="text-[10.5px] text-muted">
                Current session theme: <span className="font-medium text-ink">{theme}</span> · stored per browser in localStorage.
              </p>
            </div>
          </div>
        </Card>

        <div className="space-y-3">
          <Card className="card-pad">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold">
              <Database size={14} aria-hidden /> Demo dataset
            </h3>
            <p className="mt-1 text-[11px] text-muted">
              Synthetic, seeded data (24 products, 12 months, weekly and seasonal patterns). Always labelled{" "}
              <code className="text-[10px]">is_demo = 1</code> and excluded when you filter to real records.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" onClick={loadDemo} loading={busyDemo}>
                {settings?.demo_rows ? "Reload demo data" : "Load demo data"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setConfirmClear(true)}
                disabled={!settings?.demo_rows}
                icon={<Trash2 size={13} aria-hidden />}
              >
                Remove demo data
              </Button>
            </div>
          </Card>

          <Card className="card-pad">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold">
              <ShieldCheck size={14} className="text-positive" aria-hidden /> System status
            </h3>
            {healthApi.loading ? (
              <LoadingBlock rows={2} />
            ) : (
              <dl className="mt-1 space-y-1 text-[11px]">
                <div className="flex justify-between">
                  <dt className="text-muted">API</dt>
                  <dd className="font-medium">{healthApi.data?.status ?? "unknown"}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Environment</dt>
                  <dd className="font-medium">{settings?.environment ?? "—"}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Sales records</dt>
                  <dd className="font-medium">{formatNumber(healthApi.data?.sales_records ?? 0)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Upload limit</dt>
                  <dd className="font-medium">{settings?.max_upload_mb ?? "—"} MB</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Data window</dt>
                  <dd className="font-medium">
                    {meta?.date_range.start ?? "—"} → {meta?.date_range.end ?? "—"}
                  </dd>
                </div>
              </dl>
            )}
            <div className="mt-2">
              <Badge tone="neutral">No authentication is enabled in this build</Badge>
            </div>
            <p className="mt-1.5 text-[10px] text-muted">
              The API has no login screen; deploy behind your own gateway or add auth before exposing it publicly.
            </p>
          </Card>
        </div>
      </div>

      {auditApi.error ? <ErrorBanner error={auditApi.error} /> : null}

      <Card>
        <CardHeader
          title="Audit trail"
          description="Imports, stock adjustments, forecast runs and recommendation decisions"
          icon={<History size={15} aria-hidden />}
        />
        {auditApi.loading && !auditApi.data ? (
          <LoadingBlock rows={5} />
        ) : (
          <DataTable
            rows={(auditApi.data?.items ?? []) as Array<Record<string, unknown>>}
            columns={[
              {
                key: "created_at",
                header: "When",
                value: (row) => String(row.created_at ?? ""),
                render: (row) => <span className="text-[11px] text-muted">{formatDateTime(String(row.created_at ?? ""))}</span>,
                sortable: true,
              },
              {
                key: "action",
                header: "Action",
                value: (row) => String(row.action ?? ""),
                render: (row) => <code className="text-[10.5px]">{String(row.action)}</code>,
                sortable: true,
              },
              {
                key: "entity_type",
                header: "Entity",
                value: (row) => `${row.entity_type} ${row.entity_id ?? ""}`,
                render: (row) => (
                  <span className="text-[11px]">
                    {String(row.entity_type)} {row.entity_id ? `#${row.entity_id}` : ""}
                  </span>
                ),
              },
              { key: "actor", header: "Actor", value: (row) => String(row.actor ?? ""), render: (row) => <span className="text-[11px]">{String(row.actor)}</span>, sortable: true },
              {
                key: "details",
                header: "Details",
                hideBelow: "md" as const,
                render: (row) => (
                  <span className="block max-w-[420px] truncate font-mono text-[10px] text-muted" title={JSON.stringify(row.details)}>
                    {JSON.stringify(row.details)}
                  </span>
                ),
              },
            ]}
            rowKey={(row) => Number(row.id)}
            pageSize={10}
            initialSort={{ key: "created_at", dir: "desc" }}
            emptyTitle="No audit entries yet"
            emptyDescription="Import a file, adjust stock or approve a recommendation to populate the trail."
            caption="Audit trail"
          />
        )}
      </Card>

      <Callout tone="info" title="Secrets and configuration">
        Database URLs, upload limits and CORS origins come from environment variables (<code>backend/.env</code>, see{" "}
        <code>.env.example</code>). No credential is stored in the database or shipped to the browser.
      </Callout>

      <Modal
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        title="Remove the demo dataset?"
        description="Only rows flagged is_demo = 1 are deleted. Imported real records, products you created and forecasts stay."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={clearDemo} loading={busyDemo}>
              Remove demo data
            </Button>
          </>
        }
      >
        <p className="text-[11.5px] text-muted">
          Demo products and their sales rows will be deleted. Any forecast or recommendation that referenced them becomes stale — rebuild
          recommendations afterwards.
        </p>
      </Modal>
    </div>
  );
}
