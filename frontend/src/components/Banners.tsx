/** Data-provenance banners and the onboarding checklist. */

import { Link } from "react-router-dom";
import { CheckCircle2, Circle, FlaskConical, ShieldCheck, Sparkles } from "lucide-react";
import { useApp } from "../context/AppContext";
import { Badge, Button, Card, cx, ProgressBar } from "./ui";
import type { ApiErrorShape } from "../lib/api";

export function DemoBanner({ demoSharePct }: { demoSharePct?: number | null }) {
  const { settings, filters } = useApp();
  const demoOnly = filters.data_source === "demo";
  const hasDemo = (settings?.demo_rows ?? 0) > 0;
  if (!hasDemo) return null;
  if (filters.data_source === "actual") return null;

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-info/30 bg-info/10 px-3 py-2 text-[11.5px] text-ink">
      <FlaskConical size={14} className="text-info" aria-hidden />
      <span className="font-medium">
        {demoOnly ? "You are viewing synthetic demo data." : "Synthetic demo data is included in these numbers."}
      </span>
      <span className="text-muted">
        {demoSharePct !== null && demoSharePct !== undefined
          ? `${demoSharePct.toFixed(0)}% of rows in this view are demo records (seeded, reproducible, labelled in the database).`
          : `${(settings?.demo_rows ?? 0).toLocaleString("en-IN")} demo rows are stored alongside your own records.`}
      </span>
      <span className="ml-auto flex items-center gap-1.5">
        <Badge tone="accent">is_demo = 1</Badge>
        {!demoOnly ? (
          <Link to="/" onClick={() => window.dispatchEvent(new Event("smartstock:resetFilters"))} className="underline decoration-dotted">
            Hide demo data
          </Link>
        ) : null}
      </span>
    </div>
  );
}

export function DemoDataAvailable({ onLoad, loading }: { onLoad: () => void; loading?: boolean }) {
  const { settings } = useApp();
  if (!settings || settings.demo_rows > 0 || settings.actual_rows > 0) return null;
  return (
    <Card className="mb-4 border-accent/30 bg-accent/5 card-pad">
      <div className="flex flex-wrap items-center gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent/15 text-accent">
          <Sparkles size={16} aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">No sales data yet</p>
          <p className="mt-0.5 text-xs text-muted">
            Import your own CSV/XLSX export, or load the labelled synthetic dataset to explore every feature immediately.
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={onLoad} loading={loading}>
            Load demo data
          </Button>
          <Link to="/import" className="btn-primary px-3 py-1.5 text-xs">
            Import a file
          </Link>
        </div>
      </div>
    </Card>
  );
}

export function ErrorBanner({ error }: { error: ApiErrorShape }) {
  return (
    <div className="mb-3 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[11.5px]" role="alert">
      <p className="font-medium text-danger">{error.message}</p>
      {error.issues?.length ? (
        <ul className="mt-1 space-y-0.5 text-muted">
          {error.issues.map((issue) => (
            <li key={issue.field}>
              <code className="text-[10px]">{issue.field}</code> — {issue.message}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function OnboardingChecklist({
  steps,
  completed,
  total,
}: {
  steps: Array<{ key: string; label: string; complete: boolean; hint: string }>;
  completed: number;
  total: number;
}) {
  if (!steps.length) return null;
  const allDone = completed === total;
  return (
    <Card className="card-pad">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Getting started</h3>
        <Badge tone={allDone ? "positive" : "accent"}>
          {completed}/{total} complete
        </Badge>
      </div>
      <ProgressBar value={completed} max={total} tone={allDone ? "positive" : "accent"} />
      <ul className="mt-3 space-y-2">
        {steps.map((step) => (
          <li key={step.key} className="flex items-start gap-2">
            {step.complete ? (
              <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-positive" aria-hidden />
            ) : (
              <Circle size={14} className="mt-0.5 shrink-0 text-muted" aria-hidden />
            )}
            <div className="min-w-0">
              <p className={cx("text-xs font-medium", step.complete ? "text-muted line-through" : "text-ink")}>{step.label}</p>
              <p className="text-[10.5px] text-muted">{step.hint}</p>
            </div>
          </li>
        ))}
      </ul>
      {!allDone ? (
        <p className="mt-3 flex items-center gap-1.5 text-[10.5px] text-muted">
          <ShieldCheck size={11} aria-hidden /> Every number in this app is computed from persisted rows — nothing is mocked.
        </p>
      ) : null}
    </Card>
  );
}
