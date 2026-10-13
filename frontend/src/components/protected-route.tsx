import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/providers/auth-provider";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  if (isLoading) return <p className="py-20 text-center text-muted">Checking your secure session…</p>;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}
