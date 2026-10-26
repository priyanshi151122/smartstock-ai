/** Axios client and typed endpoint wrappers. */

import axios, { AxiosError } from "axios";
import type {
  AppSettings,
  SalesResponse,
  DashboardResponse,
  ForecastRunDetail,
  ForecastRunSummary,
  ImportBatch,
  ImportValidateResponse,
  InventoryListResponse,
  InventoryRow,
  KpiResponse,
  MetaResponse,
  PerformanceResponse,
  Product,
  Recommendation,
  RecommendationList,
  ReportFile,
  StockMovement,
} from "./types";

export const api = axios.create({
  baseURL: "/api",
  timeout: 180_000, // forecast runs are synchronous and can take a while
  headers: { "Content-Type": "application/json" },
});

export interface ApiErrorShape {
  message: string;
  status: number;
  issues?: Array<{ field: string; message: string }>;
}

/** Convert an axios/unknown error into a friendly, actionable message. */
export function toApiError(error: unknown): ApiErrorShape {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ error?: { message?: string; issues?: Array<{ field: string; message: string }> } }>;
    if (axiosError.response) {
      const body = axiosError.response.data;
      return {
        message: body?.error?.message ?? `Request failed with status ${axiosError.response.status}.`,
        status: axiosError.response.status,
        issues: body?.error?.issues,
      };
    }
    if (axiosError.code === "ECONNABORTED") {
      return { message: "The request timed out. Forecast runs on large catalogues can take a minute — please retry.", status: 408 };
    }
    return { message: "Cannot reach the SmartStock API. Is the backend running on port 8000?", status: 0 };
  }
  if (error instanceof Error) return { message: error.message, status: 0 };
  return { message: "Unexpected error.", status: 0 };
}

export type QueryParams = Record<string, string | number | boolean | null | undefined>;

function clean(params: QueryParams = {}): QueryParams {
  const output: QueryParams = {};
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") output[key] = value;
  });
  return output;
}

export const endpoints = {
  health: () => api.get("/health").then((r) => r.data),
  settings: () => api.get<AppSettings>("/settings").then((r) => r.data),
  updateSettings: (body: Partial<AppSettings>) => api.put<AppSettings>("/settings", body).then((r) => r.data),
  meta: () => api.get<MetaResponse>("/meta").then((r) => r.data),
  auditLogs: (params: QueryParams = {}) => api.get("/audit-logs", { params: clean(params) }).then((r) => r.data),

  kpis: (params: QueryParams = {}) => api.get<KpiResponse>("/analytics/kpis", { params: clean(params) }).then((r) => r.data),
  dashboard: (params: QueryParams = {}) =>
    api.get<DashboardResponse>("/analytics/dashboard", { params: clean(params) }).then((r) => r.data),
  sales: (params: QueryParams = {}) =>
    api.get<SalesResponse>("/analytics/sales", { params: clean(params) }).then((r) => r.data),
  performance: (params: QueryParams = {}) =>
    api.get<PerformanceResponse>("/analytics/performance", { params: clean(params) }).then((r) => r.data),
  productHistory: (productId: number, params: QueryParams = {}) =>
    api.get(`/analytics/products/${productId}/history`, { params: clean(params) }).then((r) => r.data),

  products: (params: QueryParams = {}) => api.get("/products", { params: clean(params) }).then((r) => r.data),
  product: (id: number) => api.get<Product>(`/products/${id}`).then((r) => r.data),
  createProduct: (body: Partial<Product>) => api.post<Product>("/products", body).then((r) => r.data),
  updateProduct: (id: number, body: Partial<Product>) => api.patch<Product>(`/products/${id}`, body).then((r) => r.data),
  categories: () => api.get<string[]>("/categories").then((r) => r.data),
  suppliers: () => api.get("/suppliers").then((r) => r.data),

  inventory: (params: QueryParams = {}) =>
    api.get<InventoryListResponse>("/inventory", { params: clean(params) }).then((r) => r.data),
  inventorySummary: (params: QueryParams = {}) => api.get("/inventory/summary", { params: clean(params) }).then((r) => r.data),
  inventoryItem: (productId: number) => api.get<InventoryRow>(`/inventory/${productId}`).then((r) => r.data),
  updateInventory: (productId: number, body: Record<string, unknown>) =>
    api.patch<InventoryRow>(`/inventory/${productId}`, body).then((r) => r.data),
  adjustStock: (productId: number, body: { quantity_delta: number; reason: string; actor?: string; reference?: string }) =>
    api.post<InventoryRow>(`/inventory/${productId}/adjust`, body).then((r) => r.data),
  movements: (params: QueryParams = {}) =>
    api.get<StockMovement[]>("/inventory/movements", { params: clean(params) }).then((r) => r.data),

  forecastModels: () => api.get("/forecasts/models").then((r) => r.data),
  runForecast: (body: { horizon_days: number; model: string; category?: string | null; data_source?: string | null }) =>
    api.post<ForecastRunDetail>("/forecasts/run", body).then((r) => r.data),
  forecastRuns: (params: QueryParams = {}) =>
    api.get<ForecastRunSummary[]>("/forecasts/runs", { params: clean(params) }).then((r) => r.data),
  forecastRun: (id: number) => api.get<ForecastRunDetail>(`/forecasts/runs/${id}`).then((r) => r.data),
  latestForecast: () => api.get<ForecastRunDetail>("/forecasts/latest").then((r) => r.data),
  productForecast: (runId: number, productId: number) =>
    api.get(`/forecasts/runs/${runId}/products/${productId}`).then((r) => r.data),

  recommendations: (params: QueryParams = {}) =>
    api.get<RecommendationList>("/recommendations", { params: clean(params) }).then((r) => r.data),
  recommendation: (id: number) => api.get<Recommendation>(`/recommendations/${id}`).then((r) => r.data),
  generateRecommendations: (body: Record<string, unknown> = {}) =>
    api.post("/recommendations/generate", body).then((r) => r.data),
  decideRecommendation: (id: number, body: { status: "approved" | "dismissed"; note?: string; actor?: string }) =>
    api.post<Recommendation>(`/recommendations/${id}/decision`, body).then((r) => r.data),

  importFields: () => api.get("/imports/fields").then((r) => r.data),
  uploadSales: (file: File, dataSource: "actual" | "demo") => {
    const form = new FormData();
    form.append("file", file);
    form.append("data_source", dataSource);
    return api.post<ImportValidateResponse>("/imports/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
    }).then((r) => r.data);
  },
  revalidate: (batchId: number, body: { mapping?: Record<string, string | null>; cleaning?: string[] }) =>
    api.post<ImportValidateResponse>(`/imports/${batchId}/revalidate`, body).then((r) => r.data),
  commitImport: (body: { batch_id: number; apply_cleaning?: string[]; skip_duplicates?: boolean; data_source?: string }) =>
    api.post("/imports/commit", body).then((r) => r.data),
  importHistory: (params: QueryParams = {}) => api.get<ImportBatch[]>("/imports/history", { params: clean(params) }).then((r) => r.data),
  templateUrl: (format: "csv" | "xlsx" = "csv") => `/api/imports/template?format=${format}`,
  validationReportUrl: (batchId: number) => `/api/imports/${batchId}/report`,

  reportTypes: () => api.get("/reports/types").then((r) => r.data),
  generateReport: (body: Record<string, unknown>) => api.post<ReportFile>("/reports", body).then((r) => r.data),
  reports: (params: QueryParams = {}) => api.get<ReportFile[]>("/reports", { params: clean(params) }).then((r) => r.data),

  loadDemo: (seed?: number) => api.post("/demo/load", null, { params: clean({ seed }) }).then((r) => r.data),
  clearDemo: () => api.post("/demo/clear").then((r) => r.data),

  downloadBlob: (url: string) => api.get(url.replace(/^\/api/, ""), { responseType: "blob" }).then((r) => r.data as Blob),
};

export function downloadUrl(url: string, filename?: string): void {
  const anchor = document.createElement("a");
  anchor.href = url;
  if (filename) anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
