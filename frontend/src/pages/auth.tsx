import { useState, type FormEvent } from "react";
import { ArrowLeft, LoaderCircle } from "lucide-react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ThemeToggle } from "@/components/theme-toggle";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/providers/auth-provider";

export function LoginPage() { return <AuthPage mode="login" />; }
export function RegisterPage() { return <AuthPage mode="register" />; }

function AuthPage({ mode }: { mode: "login" | "register" }) {
  const navigate = useNavigate();
  const { user, login, register } = useAuth();
  const [error, setError] = useState("");
  const isRegister = mode === "register";
  if (user) return <Navigate to="/dashboard" replace />;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    const input = { username: String(form.get("username") || ""), password: String(form.get("password") || "") };
    try {
      if (isRegister) await register.mutateAsync({ ...input, business_name: String(form.get("business_name") || "") });
      else await login.mutateAsync(input);
      navigate("/dashboard");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "We could not connect right now. Please try again.");
    }
  }

  const busy = login.isPending || register.isPending;
  return <main className="grid min-h-screen place-items-center p-5"><div className="absolute right-5 top-5"><ThemeToggle /></div><Card className="w-full max-w-md p-6 sm:p-8"><Link to="/" className="inline-flex items-center gap-2 text-sm font-medium text-muted hover:text-ink"><ArrowLeft size={16} /> Back to home</Link><div className="mt-8"><span className="grid h-10 w-10 place-items-center rounded-xl bg-brand font-bold text-white">B</span><h1 className="mt-5 text-2xl font-bold">{isRegister ? "Create your BizIntel account" : "Welcome back"}</h1><p className="mt-2 text-muted">{isRegister ? "Start with the business files you already use." : "Log in to see your business information."}</p></div><form className="mt-7 space-y-5" onSubmit={handleSubmit}>{isRegister && <Field label="Business name" name="business_name" autoComplete="organization" />}<Field label="Username" name="username" autoComplete="username" /><Field label="Password" name="password" type="password" autoComplete={isRegister ? "new-password" : "current-password"} />{error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}<Button className="w-full" type="submit" disabled={busy}>{busy && <LoaderCircle className="animate-spin" size={17} />}{isRegister ? "Create account" : "Log in"}</Button></form><p className="mt-6 text-center text-sm text-muted">{isRegister ? "Already have an account?" : "New to BizIntel?"} <Link className="font-semibold text-brand hover:underline" to={isRegister ? "/login" : "/register"}>{isRegister ? "Log in" : "Create an account"}</Link></p></Card></main>;
}

function Field({ label, name, type = "text", autoComplete }: { label: string; name: string; type?: string; autoComplete?: string }) {
  return <label className="block text-sm font-medium">{label}<Input className="mt-2" name={name} type={type} autoComplete={autoComplete} required /></label>;
}
