import { ArrowRight, ChartNoAxesCombined, ShieldCheck, Sparkles, Upload } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ThemeToggle } from "@/components/theme-toggle";

const benefits = [
  { icon: Upload, title: "Bring your files", text: "Add sales and expense files without changing how you already work." },
  { icon: ChartNoAxesCombined, title: "See the important numbers", text: "Revenue, spending, and profit in one calm, clear place." },
  { icon: Sparkles, title: "Ask in plain language", text: "Get answers from your own records, with the source numbers shown." },
];

export function LandingPage() {
  return <div className="min-h-screen overflow-hidden">
    <header className="page-wrap flex h-20 items-center justify-between"><Link to="/" className="flex items-center gap-2 font-bold"><span className="grid h-9 w-9 place-items-center rounded-xl bg-brand text-white">B</span> BizIntel</Link><div className="flex items-center gap-2"><ThemeToggle /><Button asChild variant="ghost"><Link to="/login">Log in</Link></Button><Button asChild><Link to="/register">Get started</Link></Button></div></header>
    <main id="main-content">
      <section className="page-wrap grid gap-12 py-16 lg:grid-cols-[1.1fr_.9fr] lg:items-center lg:py-24">
        <div><p className="eyebrow">For small businesses that want clarity</p><h1 className="mt-5 max-w-3xl text-4xl font-bold leading-tight tracking-tight sm:text-6xl">Understand your business. <span className="text-brand">Decide with confidence.</span></h1><p className="mt-6 max-w-xl text-lg leading-8 text-muted">BizIntel turns the files you already have into a simple view of your revenue, costs, profit, and next steps.</p><div className="mt-8 flex flex-wrap gap-3"><Button asChild size="lg"><Link to="/register">Start with your files <ArrowRight size={18} /></Link></Button><Button asChild variant="outline" size="lg"><Link to="/login">I already have an account</Link></Button></div><p className="mt-5 flex items-center gap-2 text-sm text-muted"><ShieldCheck size={16} className="text-brand" /> Your business data stays separate from every other business.</p></div>
        <Card className="relative overflow-hidden p-6 sm:p-8"><div className="absolute -right-20 -top-20 h-56 w-56 rounded-full bg-blue-100 blur-3xl dark:bg-blue-950" /><div className="relative flex items-center justify-between"><p className="text-sm font-medium text-muted">This month at a glance</p><span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-muted dark:bg-slate-800">Example</span></div><div className="relative mt-5 grid grid-cols-2 gap-4"><Metric label="Revenue (Example)" value="₹4,82,600" /><Metric label="Expenses (Example)" value="₹2,96,400" /><Metric label="Profit (Example)" value="₹1,86,200" strong /><Metric label="Average order (Example)" value="₹684" /></div><div className="relative mt-5 rounded-xl border bg-slate-50 p-4 dark:bg-slate-900"><div className="h-24 rounded-lg bg-[linear-gradient(135deg,transparent_0%,transparent_20%,hsl(var(--brand)/.14)_20%,hsl(var(--brand)/.14)_22%,transparent_22%),linear-gradient(to_top_right,transparent_49%,hsl(var(--brand))_50%,transparent_51%)]" /><p className="mt-3 text-sm text-muted">A simple daily revenue view with example numbers, ready when you are.</p></div></Card>
      </section>
      <section className="page-wrap py-14"><p className="eyebrow text-center">Built around your everyday work</p><div className="mt-8 grid gap-5 md:grid-cols-3">{benefits.map(({ icon: Icon, title, text }) => <Card key={title} className="p-6"><span className="grid h-11 w-11 place-items-center rounded-xl bg-blue-50 text-brand dark:bg-blue-950"><Icon size={21} /></span><h2 className="mt-5 text-lg font-semibold">{title}</h2><p className="mt-2 leading-7 text-muted">{text}</p></Card>)}</div></section>
      <section className="border-y bg-surface py-16"><div className="page-wrap"><p className="eyebrow">How it works</p><h2 className="mt-3 text-3xl font-bold">From file to useful answer in three steps.</h2><div className="mt-10 grid gap-7 md:grid-cols-3">{["Upload your sales and expense files.", "Check the columns we found together.", "Use your dashboard and ask questions."].map((step, index) => <div key={step} className="flex gap-4"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand font-bold text-white">{index + 1}</span><p className="pt-1 leading-7 text-muted">{step}</p></div>)}</div></div></section>
      <section className="page-wrap py-16 text-center"><h2 className="text-3xl font-bold">Ready to see the full picture?</h2><p className="mx-auto mt-3 max-w-xl text-muted">Create your account and import the files you already use to run your business.</p><Button asChild size="lg" className="mt-7"><Link to="/register">Create an account <ArrowRight size={18} /></Link></Button></section>
    </main>
  </div>;
}

function Metric({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return <div className="rounded-xl border bg-surface p-4"><p className="text-sm text-muted">{label}</p><p className={`mt-2 text-xl font-bold ${strong ? "text-brand" : ""}`}>{value}</p></div>;
}
