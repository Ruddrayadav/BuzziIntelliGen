import { Bot, LayoutDashboard, Upload } from "lucide-react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/app-shell";
import { ProtectedRoute } from "@/components/protected-route";
import { LandingPage } from "@/pages/landing";
import { LoginPage, RegisterPage } from "@/pages/auth";
import { PlaceholderPage } from "@/pages/placeholder";
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
      <Route path="/upload" element={<PlaceholderPage icon={Upload} title="Bring in your business files" description="The guided upload experience arrives in the next step." />} />
      <Route path="/dashboard" element={<PlaceholderPage icon={LayoutDashboard} title="Your dashboard is getting ready" description="Once your files are imported, this is where you will see the numbers that matter." next={{ to: "/upload", label: "Upload files" }} />} />
      <Route path="/ask" element={<PlaceholderPage icon={Bot} title="Ask about your business" description="The Ask AI conversation experience arrives in a later step." />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></BrowserRouter></AuthProvider></ThemeProvider></QueryProvider>;
}
