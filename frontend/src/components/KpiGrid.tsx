/** KPI cards with honest states for unavailable metrics. */

import { ArrowDownRight, ArrowUpRight, HelpCircle, Info, Minus } from "lucide-react";
import type { KpiCard } from "../lib/types";
import { cx, Skeleton } from "./ui";
import { formatPercent } from "../lib/format";

const TONE_RING: Record<string, string> = {
  neutral: "border-line",
  positive: "border-positive/30",
  warning: "border-warning/30",
  danger: "border-danger/30",
};

export function KpiGrid({ cards, loading }: { cards: KpiCard[]; loading?: boolean }) {
  if (loading && !cards.length) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="card p-4">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="mt-3 h-6 w-32" />
            <Skeleton className="mt-3 h-3 w-20" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <article
          key={card.key}
          className={cx("card p-4 transition hover:shadow-pop", TONE_RING[card.tone ?? "neutral"])}
          aria-label={card.label}
        >
          <div className="flex items-start justify-between gap-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{card.label}</p>
            {!card.available ? (
              <span title={card.note ?? "Not enough data"} aria-label="Not enough data">
                <HelpCircle size={13} className="text-muted" aria-hidden />
              </span>
            ) : null}
          </div>

          <p
            className={cx(
              "mt-1.5 text-2xl font-semibold tabular-nums tracking-tight",
              card.available ? "text-ink" : "text-muted/70",
            )}
          >
            {card.available ? card.formatted : "Not available"}
          </p>

          <div className="mt-2 flex min-h-[18px] flex-wrap items-center gap-1.5 text-[11px]">
            {card.change_pct !== null && card.change_pct !== undefined ? (
              <span
                className={cx(
                  "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-medium",
                  card.change_pct > 0
                    ? "bg-positive/10 text-positive"
                    : card.change_pct < 0
                      ? "bg-danger/10 text-danger"
                      : "bg-elevated text-muted",
                )}
              >
                {card.change_pct > 0 ? (
                  <ArrowUpRight size={11} aria-hidden />
                ) : card.change_pct < 0 ? (
                  <ArrowDownRight size={11} aria-hidden />
                ) : (
                  <Minus size={11} aria-hidden />
                )}
                {formatPercent(card.change_pct)}
              </span>
            ) : null}
            {card.comparison_label ? <span className="text-muted">{card.comparison_label}</span> : null}
          </div>

          {!card.available && card.note ? (
            <p className="mt-1.5 flex items-start gap-1 text-[10.5px] leading-snug text-muted">
              <Info size={10} className="mt-0.5 shrink-0" aria-hidden />
              {card.note}
            </p>
          ) : null}
        </article>
      ))}
    </div>
  );
}
