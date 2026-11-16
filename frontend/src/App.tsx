import { lazy, Suspense } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./components/layout";
import { Button, LoadingBlock } from "./components/ui";
import { LoginPage, RegisterPage } from "./pages/AuthPages";
import DashboardPage from "./pages/DashboardPage";
import TendersPage from "./pages/TendersPage";

const TenderDetailPage = lazy(() => import("./pages/TenderDetailPage"));
const ProposalEditorPage = lazy(() => import("./pages/ProposalEditorPage"));
const TasksPage = lazy(() => import("./pages/TasksPage"));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));
const ExportsPage = lazy(() => import("./pages/ExportsPage"));
const CompanyProfilePage = lazy(() => import("./pages/CompanyProfilePage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

function NotFound() {
  return (
    <div className="mx-auto max-w-md py-20 text-center">
      <p className="text-sm font-medium text-accent-700">404</p>
      <h1 className="mt-2 text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-sm text-muted">The page you are looking for does not exist or you do not have access to it.</p>
      <Link to="/">
        <Button className="mt-6">Back to dashboard</Button>
      </Link>
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<div className="p-8"><LoadingBlock /></div>}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route element={<RequireAuth />}>
          <Route index element={<DashboardPage />} />
          <Route path="tenders" element={<TendersPage />} />
          <Route path="tenders/:tenderId" element={<TenderDetailPage />} />
          <Route path="tenders/:tenderId/proposals/:proposalId" element={<ProposalEditorPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="exports" element={<ExportsPage />} />
          <Route path="company" element={<CompanyProfilePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
