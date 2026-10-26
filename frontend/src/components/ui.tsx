/** Reusable, accessible UI primitives. */

import {
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  useEffect,
  useId,
  useRef,
} from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2, RefreshCw, X } from "lucide-react";
import type { ApiErrorShape } from "../lib/api";
import type { RiskLevel } from "../lib/types";

export function cx(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}

export function Card({
  children,
  className,
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article";
}) {
  return <Tag className={cx("card", className)}>{children}</Tag>;
}

export function CardHeader({
  title,
  description,
  actions,
  icon,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
      <div className="flex min-w-0 items-start gap-2.5">
        {icon ? <span className="mt-0.5 text-muted">{icon}</span> : null}
        <div className="min-w-0">
          <h2 className="truncate text-[15px] font-semibold text-ink">{title}</h2>
          {description ? <p className="mt-0.5 text-xs text-muted">{description}</p> : null}
        </div>
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  children,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
  icon?: ReactNode;
}) {
  const variantClass = {
    primary: "btn-primary",
    secondary: "btn-secondary",
    ghost: "btn-ghost",
    danger: "btn-danger",
  }[variant];
  return (
    <button
      className={cx(variantClass, size === "sm" && "px-2.5 py-1.5 text-xs", className)}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading ? <Loader2 size={14} className="animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
  required,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
  htmlFor?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>
        {label}
        {required ? <span className="ml-0.5 text-danger">*</span> : null}
      </label>
      {children}
      {error ? (
        <p className="mt-1 text-[11px] text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1 text-[11px] text-muted">{hint}</p>
      ) : null}
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx("input", props.className)} {...props} />;
}

export function Select({ children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx("input pr-8", props.className)} {...props}>
      {children}
    </select>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  description,
  id,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
  id?: string;
}) {
  const generatedId = useId();
  const switchId = id ?? generatedId;
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <label htmlFor={switchId} className="text-sm font-medium text-ink">
          {label}
        </label>
        {description ? <p className="mt-0.5 text-xs text-muted">{description}</p> : null}
      </div>
      <button
        id={switchId}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={cx(
          "relative mt-0.5 h-6 w-11 shrink-0 rounded-full border transition",
          checked ? "border-accent bg-accent" : "border-line bg-elevated",
        )}
      >
        <span
          className={cx(
            "absolute top-0.5 h-4.5 w-4.5 rounded-full bg-white shadow transition-all",
            checked ? "left-[22px]" : "left-0.5",
          )}
          style={{ height: 18, width: 18 }}
        />
      </button>
    </div>
  );
}

const RISK_STYLES: Record<RiskLevel, { label: string; className: string }> = {
  stockout: { label: "Stockout", className: "border-danger/40 bg-danger/10 text-danger" },
  high: { label: "High risk", className: "border-warning/40 bg-warning/10 text-warning" },
  medium: { label: "Medium", className: "border-info/40 bg-info/10 text-info" },
  low: { label: "Healthy", className: "border-positive/40 bg-positive/10 text-positive" },
  overstock: { label: "Overstock", className: "border-accent/40 bg-accent/10 text-accent" },
  unknown: { label: "Unknown", className: "border-line bg-elevated text-muted" },
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  const style = RISK_STYLES[level] ?? RISK_STYLES.unknown;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium",
        style.className,
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {style.label}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "approved"
      ? "border-positive/40 bg-positive/10 text-positive"
      : status === "dismissed"
        ? "border-line bg-elevated text-muted"
        : status === "imported"
          ? "border-positive/40 bg-positive/10 text-positive"
          : status === "failed"
            ? "border-danger/40 bg-danger/10 text-danger"
            : "border-warning/40 bg-warning/10 text-warning";
  return <span className={cx("rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize", tone)}>{status}</span>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "accent" | "positive" | "warning" | "danger" }) {
  const tones = {
    neutral: "border-line bg-elevated text-muted",
    accent: "border-accent/40 bg-accent/10 text-accent",
    positive: "border-positive/40 bg-positive/10 text-positive",
    warning: "border-warning/40 bg-warning/10 text-warning",
    danger: "border-danger/40 bg-danger/10 text-danger",
  };
  return <span className={cx("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium", tones[tone])}>{children}</span>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} aria-hidden />;
}

export function LoadingBlock({ label = "Loading", rows = 4 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-3 p-4" role="status" aria-live="polite" aria-label={label}>
      <span className="sr-only">{label}…</span>
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className={cx("h-4", index === 0 ? "w-1/3" : index % 2 ? "w-3/4" : "w-full")} />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
      <span className="grid h-11 w-11 place-items-center rounded-full border border-line bg-elevated text-muted">
        {icon ?? <Info size={18} aria-hidden />}
      </span>
      <div>
        <p className="text-sm font-medium text-ink">{title}</p>
        {description ? <p className="mx-auto mt-1 max-w-md text-xs text-muted">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiErrorShape; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-10 text-center" role="alert">
      <span className="grid h-11 w-11 place-items-center rounded-full border border-danger/40 bg-danger/10 text-danger">
        <AlertTriangle size={18} aria-hidden />
      </span>
      <div>
        <p className="text-sm font-medium text-ink">Something needs attention</p>
        <p className="mx-auto mt-1 max-w-md text-xs text-muted">{error.message}</p>
        {error.issues?.length ? (
          <ul className="mt-2 space-y-1 text-left text-[11px] text-muted">
            {error.issues.slice(0, 3).map((issue) => (
              <li key={issue.field}>
                <span className="font-mono text-[10px] text-danger">{issue.field}</span>: {issue.message}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry} icon={<RefreshCw size={13} aria-hidden />}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function Callout({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "warning" | "danger" | "success";
  title?: string;
  children: ReactNode;
}) {
  const styles = {
    info: "border-info/30 bg-info/10 text-info",
    warning: "border-warning/30 bg-warning/10 text-warning",
    danger: "border-danger/30 bg-danger/10 text-danger",
    success: "border-positive/30 bg-positive/10 text-positive",
  }[tone];
  const Icon = tone === "danger" ? AlertTriangle : tone === "success" ? CheckCircle2 : tone === "warning" ? AlertTriangle : Info;
  return (
    <div className={cx("flex gap-2.5 rounded-lg border p-3 text-xs", styles)}>
      <Icon size={15} className="mt-0.5 shrink-0" aria-hidden />
      <div className="min-w-0 space-y-1 text-ink/90">
        {title ? <p className="font-medium text-ink">{title}</p> : null}
        <div className="text-[11px] leading-relaxed text-muted">{children}</div>
      </div>
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = "max-w-lg",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab" && dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        } else if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.setTimeout(() => {
      dialogRef.current?.querySelector<HTMLElement>("button, input, select, textarea")?.focus();
    }, 30);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/60 p-0 backdrop-blur-sm sm:items-center sm:p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={dialogRef}
        className={cx("w-full animate-fade-in rounded-t-2xl border border-line bg-surface shadow-pop sm:rounded-xl2", width)}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-3.5">
          <div>
            <h2 id={titleId} className="text-sm font-semibold text-ink">
              {title}
            </h2>
            {description ? <p className="mt-0.5 text-xs text-muted">{description}</p> : null}
          </div>
          <button type="button" onClick={onClose} className="btn-ghost -mr-1 p-1.5" aria-label="Close dialog">
            <X size={16} aria-hidden />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4 scroll-thin">{children}</div>
        {footer ? <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</div> : null}
      </div>
    </div>
  );
}

export function StatPill({ label, value, tone = "neutral" }: { label: string; value: ReactNode; tone?: "neutral" | "good" | "bad" | "warn" }) {
  const tones = {
    neutral: "text-ink",
    good: "text-positive",
    bad: "text-danger",
    warn: "text-warning",
  };
  return (
    <div className="rounded-lg border border-line bg-elevated px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-muted">{label}</p>
      <p className={cx("mt-0.5 text-sm font-semibold tabular-nums", tones[tone])}>{value}</p>
    </div>
  );
}

export function ProgressBar({ value, max = 100, tone = "accent" }: { value: number; max?: number; tone?: "accent" | "positive" | "warning" | "danger" }) {
  const percent = Math.max(0, Math.min(100, max ? (value / max) * 100 : 0));
  const colors = { accent: "bg-accent", positive: "bg-positive", warning: "bg-warning", danger: "bg-danger" };
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={Math.round(percent)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cx("h-full rounded-full transition-all", colors[tone])} style={{ width: `${percent}%` }} />
    </div>
  );
}
