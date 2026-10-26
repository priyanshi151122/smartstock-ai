/** Recharts wrappers with theme-aware colours, tooltips and accessible fallbacks. */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useApp } from "../context/AppContext";
import { formatCompact, formatCurrency, formatDate, formatNumber, formatPeriodLabel } from "../lib/format";

const PALETTE = ["#2563eb", "#0ea5e9", "#14b8a6", "#f59e0b", "#a855f7", "#ef4444", "#22c55e", "#64748b"];

function useChartTheme() {
  const { theme } = useApp();
  const dark = theme === "dark";
  return {
    dark,
    grid: dark ? "#26324e" : "#e2e8f0",
    axis: dark ? "#94a3b8" : "#64748b",
    primary: dark ? "#60a5fa" : "#2563eb",
    secondary: dark ? "#38bdf8" : "#0ea5e9",
    positive: dark ? "#34d399" : "#16a34a",
    warning: dark ? "#fbbf24" : "#d97706",
    danger: dark ? "#f87171" : "#dc2626",
    surface: dark ? "#0f1627" : "#ffffff",
    text: dark ? "#e2e8f0" : "#0f172a",
    muted: dark ? "#94a3b8" : "#64748b",
  };
}

function TooltipBox({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number | string; color?: string; dataKey?: string }>;
  label?: string;
  formatter?: (value: number, key: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface/95 px-2.5 py-2 text-[11px] shadow-pop backdrop-blur">
      <p className="mb-1 font-medium text-ink">{label}</p>
      <ul className="space-y-0.5">
        {payload.map((entry) => (
          <li key={`${entry.dataKey}-${entry.name}`} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1.5 text-muted">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: entry.color }} aria-hidden />
              {entry.name}
            </span>
            <span className="font-medium tabular-nums text-ink">
              {formatter
                ? formatter(Number(entry.value ?? 0), String(entry.dataKey ?? ""))
                : formatNumber(Number(entry.value ?? 0))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SalesTrendChart({
  data,
  granularity,
  height = 280,
  showUnits = true,
}: {
  data: Array<{ period: string; revenue: number; units: number }>;
  granularity?: string;
  height?: number;
  showUnits?: boolean;
}) {
  const theme = useChartTheme();
  const { currency } = useApp();
  return (
    <div style={{ height }} role="img" aria-label="Revenue and units over time">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={theme.primary} stopOpacity={0.35} />
              <stop offset="100%" stopColor={theme.primary} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={theme.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="period"
            tick={{ fontSize: 10, fill: theme.axis }}
            tickLine={false}
            axisLine={{ stroke: theme.grid }}
            tickFormatter={(value: string) => formatPeriodLabel(value, granularity)}
            minTickGap={16}
          />
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 10, fill: theme.axis }}
            tickLine={false}
            axisLine={false}
            width={58}
            tickFormatter={(value: number) => formatCompact(value)}
          />
          {showUnits ? (
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fontSize: 10, fill: theme.axis }}
              tickLine={false}
              axisLine={false}
              width={46}
              tickFormatter={(value: number) => formatCompact(value)}
            />
          ) : null}
          <Tooltip
            content={
              <TooltipBox
                formatter={(value, key) =>
                  key === "revenue" ? formatCurrency(value, { symbol: currency.symbol, locale: currency.locale }) : formatNumber(value)
                }
              />
            }
          />
          <Area
            yAxisId="left"
            type="monotone"
            dataKey="revenue"
            name="Revenue"
            stroke={theme.primary}
            strokeWidth={2}
            fill="url(#revenueFill)"
            dot={false}
            activeDot={{ r: 3 }}
          />
          {showUnits ? (
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="units"
              name="Units"
              stroke={theme.secondary}
              strokeWidth={1.6}
              strokeDasharray="4 3"
              dot={false}
            />
          ) : null}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CategoryBarChart({
  data,
  height = 280,
}: {
  data: Array<{ category: string; revenue: number; units: number; share?: number }>;
  height?: number;
}) {
  const theme = useChartTheme();
  const { currency } = useApp();
  return (
    <div style={{ height }} role="img" aria-label="Revenue by category">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
          <CartesianGrid stroke={theme.grid} strokeDasharray="3 3" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fontSize: 10, fill: theme.axis }}
            tickFormatter={(value: number) => formatCompact(value)}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="category"
            width={110}
            tick={{ fontSize: 10, fill: theme.axis }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            content={
              <TooltipBox
                formatter={(value) => formatCurrency(value, { symbol: currency.symbol, locale: currency.locale })}
              />
            }
            cursor={{ fill: theme.grid, fillOpacity: 0.25 }}
          />
          <Bar dataKey="revenue" name="Revenue" radius={[0, 4, 4, 0]} maxBarSize={22}>
            {data.map((entry, index) => (
              <Cell key={entry.category} fill={PALETTE[index % PALETTE.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function StockVsForecastChart({
  data,
  height = 300,
}: {
  data: Array<{ name: string; current_stock: number; forecast_demand: number; reorder_point: number }>;
  height?: number;
}) {
  const theme = useChartTheme();
  return (
    <div style={{ height }} role="img" aria-label="Current stock versus forecast demand">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 46, left: 4 }} barGap={2} barCategoryGap="22%">
          <CartesianGrid stroke={theme.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 9, fill: theme.axis }}
            interval={0}
            angle={-32}
            textAnchor="end"
            height={58}
            tickLine={false}
            axisLine={{ stroke: theme.grid }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: theme.axis }}
            tickFormatter={(value: number) => formatCompact(value)}
            axisLine={false}
            tickLine={false}
            width={46}
          />
          <Tooltip content={<TooltipBox />} cursor={{ fill: theme.grid, fillOpacity: 0.25 }} />
          <Legend wrapperStyle={{ fontSize: 11, color: theme.muted }} iconType="circle" iconSize={7} />
          <Bar dataKey="current_stock" name="Current stock" fill={theme.primary} radius={[3, 3, 0, 0]} maxBarSize={16} />
          <Bar dataKey="forecast_demand" name="Forecast demand" fill={theme.warning} radius={[3, 3, 0, 0]} maxBarSize={16} />
          <Line
            type="stepAfter"
            dataKey="reorder_point"
            name="Reorder point"
            stroke={theme.danger}
            strokeWidth={1.5}
            dot={false}
            strokeDasharray="5 3"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ForecastChart({
  data,
  height = 300,
}: {
  data: Array<{ period: string; actual: number | null; forecast: number | null; lower?: number | null; upper?: number | null }>;
  height?: number;
}) {
  const theme = useChartTheme();
  return (
    <div style={{ height }} role="img" aria-label="History and forecast">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={theme.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="period"
            tick={{ fontSize: 9, fill: theme.axis }}
            tickFormatter={(value: string) => formatDate(value).slice(0, 6)}
            minTickGap={22}
            tickLine={false}
            axisLine={{ stroke: theme.grid }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: theme.axis }}
            tickFormatter={(value: number) => formatCompact(value)}
            axisLine={false}
            tickLine={false}
            width={44}
          />
          <Tooltip content={<TooltipBox />} />
          <Legend wrapperStyle={{ fontSize: 11, color: theme.muted }} iconType="circle" iconSize={7} />
          <Line type="monotone" dataKey="actual" name="Actual units" stroke={theme.primary} strokeWidth={1.8} dot={false} connectNulls={false} />
          <Line type="monotone" dataKey="forecast" name="Forecast units" stroke={theme.warning} strokeWidth={2} strokeDasharray="5 3" dot={false} connectNulls={false} />
          {data.some((point) => point.upper !== null && point.upper !== undefined) ? (
            <Line type="monotone" dataKey="upper" name="Upper bound" stroke={theme.muted} strokeWidth={1} strokeDasharray="2 4" dot={false} connectNulls={false} />
          ) : null}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MiniSparkline({
  data,
  dataKey = "units",
  color,
  height = 44,
}: {
  data: Array<Record<string, number | string>>;
  dataKey?: string;
  color?: string;
  height?: number;
}) {
  const theme = useChartTheme();
  const stroke = color ?? theme.primary;
  return (
    <div style={{ height }} aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <Area type="monotone" dataKey={dataKey} stroke={stroke} strokeWidth={1.5} fill={stroke} fillOpacity={0.15} dot={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export const CHART_PALETTE = PALETTE;
