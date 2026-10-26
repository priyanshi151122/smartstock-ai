/** Route table. Every page talks to the real API — nothing is mocked. */

import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { LoadingBlock } from "./components/ui";

const Overview = lazy(() => import("./pages/Overview"));
const SalesAnalytics = lazy(() => import("./pages/SalesAnalytics"));
const DemandForecasting = lazy(() => import("./pages/DemandForecasting"));
const Inventory = lazy(() => import("./pages/Inventory"));
const ProductPerformance = lazy(() => import("./pages/ProductPerformance"));
const ReorderRecommendations = lazy(() => import("./pages/ReorderRecommendations"));
const DataImport = lazy(() => import("./pages/DataImport"));
const Reports = lazy(() => import("./pages/Reports"));
const SettingsPage = lazy(() => import("./pages/Settings"));

function PageFallback() {
  return (
    <div className="card">
      <LoadingBlock label="Loading page" rows={6} />
    </div>
  );
}

export default function App() {
  return (
    <AppShell>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/sales" element={<SalesAnalytics />} />
          <Route path="/forecast" element={<DemandForecasting />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/products" element={<ProductPerformance />} />
          <Route path="/reorder" element={<ReorderRecommendations />} />
          <Route path="/import" element={<DataImport />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
