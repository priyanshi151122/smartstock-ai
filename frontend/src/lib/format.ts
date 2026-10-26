/** Formatting helpers shared across pages (unit-testable, no React). */

export interface CurrencyOptions {
  symbol?: string;
  locale?: string;
  compact?: boolean;
}

export function formatCurrency(value: number | null | undefined, options: CurrencyOptions = {}): string {
  const { symbol = "\u20b9", locale = "en-IN", compact = true } = options;
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const absolute = Math.abs(value);
  if (compact && absolute >= 10_000_000) return `${symbol}${(value / 10_000_000).toFixed(2)} Cr`;
  if (compact && absolute >= 100_000) return `${symbol}${(value / 100_000).toFixed(2)} L`;
  return `${symbol}${new Intl.NumberFormat(locale, { maximumFractionDigits: absolute < 100 ? 2 : 0 }).format(value)}`;
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return formatNumber(value, Number.isInteger(value) ? 0 : 1);
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function formatRatioAsPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "2-digit" });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-IN", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatPeriodLabel(period: string, granularity?: string): string {
  if (!period) return "—";
  if (granularity === "month" || /^\d{4}-\d{2}$/.test(period)) {
    const [year, month] = period.split("-");
    const date = new Date(Number(year), Number(month) - 1, 1);
    return date.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
  }
  return formatDate(period);
}

export function isoDate(offsetDays = 0): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  return date.toISOString().slice(0, 10);
}

export function daysBetween(start: string | null, end: string | null): number | null {
  if (!start || !end) return null;
  const diff = new Date(end).getTime() - new Date(start).getTime();
  if (Number.isNaN(diff)) return null;
  return Math.round(diff / 86_400_000) + 1;
}

export function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function initials(value: string): string {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
