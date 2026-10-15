import { BarChart3, Bot, History, LogOut, Upload } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/providers/auth-provider";
import { cn } from "@/lib/utils";

const links = [
  { to: "/upload", label: "Upload", icon: Upload },
  { to: "/history", label: "History", icon: History },
  { to: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { to: "/ask", label: "Ask AI", icon: Bot },
];

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return <div className="min-h-screen">
    <header className="sticky top-0 z-10 border-b bg-[hsl(var(--page)/0.9)] backdrop-blur">
      <div className="page-wrap flex h-16 items-center justify-between gap-3">
        <NavLink to="/dashboard" className="flex items-center gap-2 font-bold"><span className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-white">B</span> BizIntel</NavLink>
        <nav className="hidden items-center gap-1 md:flex" aria-label="Main navigation">{links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} className={({ isActive }) => cn("rounded-lg px-3 py-2 text-sm font-medium", isActive ? "bg-slate-100 text-ink dark:bg-slate-800" : "text-muted hover:text-ink")}><span className="inline-flex items-center gap-2"><Icon size={16} />{label}</span></NavLink>)}</nav>
        <div className="flex items-center gap-1"><span className="hidden text-sm text-muted sm:inline">{user?.business_name}</span><ThemeToggle /><Button variant="ghost" size="sm" onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/") })} aria-label="Log out"><LogOut size={17} /></Button></div>
      </div>
    </header>
    <main id="main-content" className="page-wrap py-10"><Outlet /></main>
  </div>;
}
