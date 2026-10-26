/** Global app state: theme, settings, shared dashboard filters and toasts. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { endpoints } from "../lib/api";
import { useApi, useLocalState } from "../lib/hooks";
import type { AppSettings, DataSource, MetaResponse } from "../lib/types";

export type Theme = "dark" | "light";

export interface Filters {
  start_date: string | null;
  end_date: string | null;
  category: string | null;
  product_id: number | null;
  data_source: DataSource | null;
  preset: FilterPreset;
}

export type FilterPreset = "7d" | "30d" | "90d" | "12m" | "all" | "custom";

export interface Toast {
  id: number;
  title: string;
  description?: string;
  tone: "success" | "error" | "info";
}

interface AppContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  settings: AppSettings | null;
  settingsLoading: boolean;
  meta: MetaResponse | null;
  refreshMeta: () => void;
  refreshSettings: () => void;
  filters: Filters;
  setFilters: (patch: Partial<Filters>) => void;
  applyPreset: (preset: FilterPreset) => void;
  resetFilters: () => void;
  filterParams: Record<string, string | number | null>;
  currency: { symbol: string; locale: string };
  toasts: Toast[];
  pushToast: (toast: Omit<Toast, "id">) => void;
  dismissToast: (id: number) => void;
}

const DEFAULT_FILTERS: Filters = {
  start_date: null,
  end_date: null,
  category: null,
  product_id: null,
  data_source: null,
  preset: "12m",
};

const AppContext = createContext<AppContextValue | null>(null);

function presetRange(preset: FilterPreset): { start_date: string | null; end_date: string | null } {
  const today = new Date();
  const iso = (date: Date) => date.toISOString().slice(0, 10);
  const daysAgo = (days: number) => {
    const copy = new Date(today);
    copy.setDate(copy.getDate() - days);
    return iso(copy);
  };
  switch (preset) {
    case "7d":
      return { start_date: daysAgo(7), end_date: iso(today) };
    case "30d":
      return { start_date: daysAgo(30), end_date: iso(today) };
    case "90d":
      return { start_date: daysAgo(90), end_date: iso(today) };
    case "12m":
      return { start_date: daysAgo(365), end_date: iso(today) };
    case "all":
      return { start_date: null, end_date: null };
    default:
      return { start_date: null, end_date: null };
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useLocalState<Theme>("smartstock.theme", "dark");
  const [filters, setFiltersState] = useLocalState<Filters>("smartstock.filters", {
    ...DEFAULT_FILTERS,
    ...presetRange("12m"),
  });
  const [toasts, setToasts] = useState<Toast[]>([]);

  const settingsApi = useApi(() => endpoints.settings(), []);
  const metaApi = useApi(() => endpoints.meta(), []);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.style.colorScheme = theme;
  }, [theme]);

  const setTheme = useCallback(
    (next: Theme) => {
      setThemeState(next);
    },
    [setThemeState],
  );

  const setFilters = useCallback(
    (patch: Partial<Filters>) => {
      setFiltersState({ ...filters, ...patch });
    },
    [filters, setFiltersState],
  );

  const applyPreset = useCallback(
    (preset: FilterPreset) => {
      if (preset === "custom") {
        setFiltersState({ ...filters, preset });
        return;
      }
      setFiltersState({ ...filters, ...presetRange(preset), preset });
    },
    [filters, setFiltersState],
  );

  const resetFilters = useCallback(() => {
    setFiltersState({ ...DEFAULT_FILTERS, ...presetRange("12m") });
  }, [setFiltersState]);

  const pushToast = useCallback((toast: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { ...toast, id }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== id));
    }, 6000);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  const filterParams = useMemo(
    () => ({
      start_date: filters.start_date,
      end_date: filters.end_date,
      category: filters.category,
      product_id: filters.product_id,
      data_source: filters.data_source,
    }),
    [filters],
  );

  const value = useMemo<AppContextValue>(
    () => ({
      theme,
      setTheme,
      toggleTheme: () => setTheme(theme === "dark" ? "light" : "dark"),
      settings: settingsApi.data,
      settingsLoading: settingsApi.loading,
      meta: metaApi.data,
      refreshMeta: metaApi.reload,
      refreshSettings: settingsApi.reload,
      filters,
      setFilters,
      applyPreset,
      resetFilters,
      filterParams,
      currency: {
        symbol: settingsApi.data?.currency_symbol ?? "\u20b9",
        locale: settingsApi.data?.currency_locale ?? "en-IN",
      },
      toasts,
      pushToast,
      dismissToast,
    }),
    [
      theme,
      setTheme,
      settingsApi.data,
      settingsApi.loading,
      settingsApi.reload,
      metaApi.data,
      metaApi.reload,
      filters,
      setFilters,
      applyPreset,
      resetFilters,
      filterParams,
      toasts,
      pushToast,
      dismissToast,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) throw new Error("useApp must be used inside <AppProvider>");
  return context;
}
