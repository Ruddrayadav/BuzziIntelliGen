import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/app-shell";
import { ProtectedRoute } from "@/components/protected-route";
import { LandingPage } from "@/pages/landing";
import { LoginPage, RegisterPage } from "@/pages/auth";
import { UploadPage } from "@/pages/upload";
import { DashboardPage } from "@/pages/dashboard";
import { AskPage } from "@/pages/ask";
import { AuthProvider } from "@/providers/auth-provider";
import { QueryProvider } from "@/providers/query-provider";
import { ThemeProvider } from "@/providers/theme-provider";

function ProtectedShell() {
  return <ProtectedRoute><AppShell /></ProtectedRoute>;
}

export function App() {
  return <QueryProvider><ThemeProvider><AuthProvider><BrowserRouter><Routes>
    <Route path="/" element={<LandingPage />} />
    <Route path="/login" element={<LoginPage />} />
    <Route path="/register" element={<RegisterPage />} />
    <Route element={<ProtectedShell />}>
      <Route path="/upload" element={<UploadPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/ask" element={<AskPage />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></BrowserRouter></AuthProvider></ThemeProvider></QueryProvider>;
}
