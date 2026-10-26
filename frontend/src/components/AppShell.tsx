/** Responsive application shell: collapsible sidebar, top bar, toast host. */

import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  BarChart3,
  Bell,
  ChevronLeft,
  ClipboardList,
  Database,
  Gauge,
  Menu,
  Moon,
  Package,
  Settings as SettingsIcon,
  ShoppingCart,
  Sparkles,
  Sun,
  TrendingUp,
  X,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { cx } from "./ui";
import { useLocalState, useMediaQuery } from "../lib/hooks";
import { formatDateTime } from "../lib/format";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  hint: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: <Gauge size={18} aria-hidden />, hint: "Executive KPIs and risk" },
  { to: "/sales", label: "Sales Analytics", icon: <BarChart3 size={18} aria-hidden />, hint: "Revenue, units, trends" },
  { to: "/forecast", label: "Demand Forecasting", icon: <TrendingUp size={18} aria-hidden />, hint: "Models, metrics, horizons" },
  { to: "/inventory", label: "Inventory", icon: <Package size={18} aria-hidden />, hint: "Stock levels and risk" },
  { to: "/products", label: "Product Performance", icon: <Sparkles size={18} aria-hidden />, hint: "ABC, growth, margin" },
  { to: "/reorder", label: "Reorder Recommendations", icon: <ShoppingCart size={18} aria-hidden />, hint: "Approve purchase drafts" },
  { to: "/import", label: "Data Import", icon: <Database size={18} aria-hidden />, hint: "Upload, validate, import" },
  { to: "/reports", label: "Reports & Exports", icon: <ClipboardList size={18} aria-hidden />, hint: "CSV, XLSX, PDF" },
  { to: "/settings", label: "Settings", icon: <SettingsIcon size={18} aria-hidden />, hint: "Store, currency, demo data" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { theme, toggleTheme, settings, meta, toasts, dismissToast } = useApp();
  const [collapsed, setCollapsed] = useLocalState("smartstock.sidebar", false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const isDesktop = useMediaQuery("(min-width: 1024px)");
  const location = useLocation();

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const activeItem = NAV_ITEMS.find((item) => (item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)));

  return (
    <div className="min-h-screen bg-bg text-ink">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to main content
      </a>

      {/* ---------------------------------------------------------- sidebar */}
      <aside
        className={cx(
          "fixed inset-y-0 left-0 z-40 flex flex-col border-r border-line bg-surface transition-all duration-200",
          collapsed && isDesktop ? "w-[76px]" : "w-[264px]",
          mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        )}
        aria-label="Primary navigation"
      >
        <div className="flex h-14 items-center justify-between gap-2 border-b border-line px-3">
          <NavLink to="/" className="flex min-w-0 items-center gap-2.5" aria-label="SmartStock AI home">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent text-sm font-bold text-white dark:text-slate-950">
              S
            </span>
            {!collapsed || !isDesktop ? (
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold leading-tight">SmartStock AI</span>
                <span className="block truncate text-[10px] text-muted">Retail intelligence</span>
              </span>
            ) : null}
          </NavLink>
          <button
            type="button"
            className="btn-ghost p-1.5 lg:hidden"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <X size={16} aria-hidden />
          </button>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2 scroll-thin">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              title={collapsed && isDesktop ? item.label : undefined}
              className={({ isActive }) =>
                cx(
                  "group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition",
                  isActive
                    ? "bg-accent/10 font-medium text-accent"
                    : "text-muted hover:bg-elevated hover:text-ink",
                  collapsed && isDesktop && "justify-center px-0",
                )
              }
            >
              <span className="shrink-0">{item.icon}</span>
              {!collapsed || !isDesktop ? <span className="truncate">{item.label}</span> : null}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-line p-2">
          {!collapsed || !isDesktop ? (
            <div className="mb-2 rounded-lg border border-line bg-elevated px-2.5 py-2 text-[11px] text-muted">
              <p className="flex items-center gap-1.5 font-medium text-ink">
                <span className="h-1.5 w-1.5 rounded-full bg-positive" aria-hidden />
                {settings?.database_dialect === "sqlite" ? "SQLite (local)" : settings?.database_dialect ?? "API"}
              </p>
              <p className="mt-0.5 truncate">
                {settings ? `${settings.actual_rows.toLocaleString("en-IN")} real · ${settings.demo_rows.toLocaleString("en-IN")} demo rows` : "Connecting…"}
              </p>
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            className={cx("btn-ghost w-full justify-start px-2.5 py-1.5 text-xs", collapsed && isDesktop && "justify-center px-0")}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <ChevronLeft size={15} className={cx("transition-transform", collapsed && "rotate-180")} aria-hidden />
            {!collapsed || !isDesktop ? <span>Collapse</span> : null}
          </button>
        </div>
      </aside>

      {mobileOpen ? (
        <div
          className="fixed inset-0 z-30 bg-slate-950/50 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden
        />
      ) : null}

      {/* ------------------------------------------------------------- main */}
      <div className={cx("flex min-h-screen flex-col transition-all duration-200", collapsed && isDesktop ? "lg:pl-[76px]" : "lg:pl-[264px]")}>
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-line bg-bg/85 px-3 backdrop-blur sm:px-5">
          <button
            type="button"
            className="btn-ghost p-1.5 lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={18} aria-hidden />
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-[15px] font-semibold sm:text-base">{activeItem?.label ?? "SmartStock AI"}</h1>
            <p className="hidden truncate text-[11px] text-muted sm:block">{activeItem?.hint}</p>
          </div>
          <div className="flex items-center gap-1.5">
            {meta?.latest_forecast_at ? (
              <span className="hidden items-center gap-1.5 rounded-full border border-line bg-elevated px-2.5 py-1 text-[11px] text-muted xl:flex">
                <Bell size={12} aria-hidden />
                Forecast {formatDateTime(meta.latest_forecast_at)}
              </span>
            ) : null}
            <button
              type="button"
              onClick={toggleTheme}
              className="btn-ghost p-2"
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            >
              {theme === "dark" ? <Sun size={16} aria-hidden /> : <Moon size={16} aria-hidden />}
            </button>
            <div className="hidden items-center gap-2 rounded-full border border-line bg-surface px-2 py-1 sm:flex">
              <span className="grid h-6 w-6 place-items-center rounded-full bg-accent/15 text-[10px] font-semibold text-accent">
                SM
              </span>
              <span className="max-w-[140px] truncate text-[11px] text-muted">{settings?.store_name ?? "Store manager"}</span>
            </div>
          </div>
        </header>

        <main id="main-content" className="flex-1 px-3 py-4 sm:px-5 sm:py-6">
          <div className="mx-auto w-full max-w-[1500px] animate-fade-in">{children}</div>
        </main>

        <footer className="border-t border-line px-4 py-3 text-[11px] text-muted sm:px-5">
          <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-2">
            <span>
              SmartStock AI v{settings?.app_version ?? "1.0.0"} · {settings?.environment ?? "development"} ·{" "}
              {settings ? `${settings.products} products` : ""}
            </span>
            <span>
              Synthetic demo data is always labelled. Forecasts are statistical estimates, not guarantees.
            </span>
          </div>
        </footer>
      </div>

      {/* ------------------------------------------------------------ toasts */}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[calc(100%-2rem)] max-w-sm flex-col gap-2" aria-live="polite">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cx(
              "pointer-events-auto animate-fade-in rounded-lg border bg-surface p-3 shadow-pop",
              toast.tone === "success" && "border-positive/40",
              toast.tone === "error" && "border-danger/40",
              toast.tone === "info" && "border-line",
            )}
            role={toast.tone === "error" ? "alert" : "status"}
          >
            <div className="flex items-start gap-2">
              <span
                className={cx(
                  "mt-0.5 h-2 w-2 shrink-0 rounded-full",
                  toast.tone === "success" ? "bg-positive" : toast.tone === "error" ? "bg-danger" : "bg-accent",
                )}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-ink">{toast.title}</p>
                {toast.description ? <p className="mt-0.5 text-[11px] text-muted">{toast.description}</p> : null}
              </div>
              <button
                type="button"
                onClick={() => dismissToast(toast.id)}
                className="text-muted hover:text-ink"
                aria-label="Dismiss notification"
              >
                <X size={14} aria-hidden />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
