import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/app-shell";
import { ProtectedRoute } from "@/components/protected-route";
import { LandingPage } from "@/pages/landing";
import { LoginPage, RegisterPage } from "@/pages/auth";
import { AuthProvider } from "@/providers/auth-provider";
import { QueryProvider } from "@/providers/query-provider";
import { ThemeProvider } from "@/providers/theme-provider";

const UploadPage = lazy(async () => ({ default: (await import("@/pages/upload")).UploadPage }));
const HistoryPage = lazy(async () => ({ default: (await import("@/pages/history")).HistoryPage }));
const DashboardPage = lazy(async () => ({ default: (await import("@/pages/dashboard")).DashboardPage }));
const AskPage = lazy(async () => ({ default: (await import("@/pages/ask")).AskPage }));

function ProtectedShell() {
  return <ProtectedRoute><AppShell /></ProtectedRoute>;
}

export function App() {
  return <QueryProvider><ThemeProvider><AuthProvider><BrowserRouter><a className="skip-link" href="#main-content">Skip to main content</a><Routes>
    <Route path="/" element={<LandingPage />} />
    <Route path="/login" element={<LoginPage />} />
    <Route path="/register" element={<RegisterPage />} />
    <Route element={<ProtectedShell />}>
      <Route path="/upload" element={<PageSuspense><UploadPage /></PageSuspense>} />
      <Route path="/history" element={<PageSuspense><HistoryPage /></PageSuspense>} />
      <Route path="/dashboard" element={<PageSuspense><DashboardPage /></PageSuspense>} />
      <Route path="/ask" element={<PageSuspense><AskPage /></PageSuspense>} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></BrowserRouter></AuthProvider></ThemeProvider></QueryProvider>;
}

function PageSuspense({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<p className="py-20 text-center text-muted" role="status">Opening this page…</p>}>{children}</Suspense>;
}
