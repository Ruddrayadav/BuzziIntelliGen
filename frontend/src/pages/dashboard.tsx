import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowDownRight, ArrowRight, ArrowUpRight, BarChart3, ChevronDown, LoaderCircle } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, ApiError, type Anomaly, type DashboardData, type PeriodComparison, type ProfitDiagnosis } from "@/lib/api";
import { money, plainDate, signedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tab = "overview" | "compare" | "unusual" | "diagnosis";
type Granularity = "daily" | "weekly" | "monthly";

const tabs: Array<{ value: Tab; label: string }> = [
  { value: "overview", label: "Overview" }, { value: "compare", label: "Compare months" },
  { value: "unusual", label: "Unusual activity" }, { value: "diagnosis", label: "Why profit changed" },
];
const palette = ["#2563eb", "#60a5fa", "#a78bfa", "#34d399", "#fbbf24", "#fb7185"];

export function DashboardPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [granularity, setGranularity] = useState<Granularity>("daily");
  const dashboard = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });
  const comparison = useQuery({ queryKey: ["analytics", "compare"], queryFn: () => api.compare() });
  const anomalies = useQuery({ queryKey: ["analytics", "anomalies"], queryFn: api.anomalies });
  const diagnosis = useQuery({ queryKey: ["analytics", "diagnosis"], queryFn: () => api.diagnosis() });

  if (dashboard.isPending) return <PageLoading />;
  if (dashboard.isError) return <PageError error={dashboard.error} retry={() => void dashboard.refetch()} />;
  const data = dashboard.data;
  const isEmpty = data.revenue_trend.length === 0 && data.expense_breakdown.length === 0;

  return <section>
    <p className="eyebrow">Business dashboard</p>
    <h1 className="mt-2 text-3xl font-bold tracking-tight">A clear view of your business.</h1>
    <p className="mt-3 text-muted">The numbers below come from the files you imported.</p>
    <div className="mt-7 flex gap-2 overflow-x-auto border-b" role="tablist" aria-label="Dashboard sections">{tabs.map((item) => <button key={item.value} role="tab" aria-selected={tab === item.value} onClick={() => setTab(item.value)} className={cn("shrink-0 border-b-2 px-3 py-3 text-sm font-semibold", tab === item.value ? "border-brand text-brand" : "border-transparent text-muted hover:text-ink")}>{item.label}</button>)}</div>
    {isEmpty ? <EmptyDashboard /> : <div className="mt-7">{tab === "overview" && <Overview data={data} comparison={comparison.data ?? null} granularity={granularity} setGranularity={setGranularity} />}{tab === "compare" && <Compare comparison={comparison.data ?? null} loading={comparison.isPending} error={comparison.error} />}{tab === "unusual" && <Unusual report={anomalies.data ?? null} loading={anomalies.isPending} error={anomalies.error} />}{tab === "diagnosis" && <Diagnosis diagnosis={diagnosis.data ?? null} loading={diagnosis.isPending} error={diagnosis.error} />}</div>}
  </section>;
}

function Overview({ data, comparison, granularity, setGranularity }: { data: DashboardData; comparison: PeriodComparison | null; granularity: Granularity; setGranularity: (value: Granularity) => void }) {
  const trendQuery = useQuery({
    queryKey: ["dashboard", "trend", granularity],
    queryFn: () => api.trend(granularity),
  });
  const trendData = trendQuery.data ?? [];

  return <div className="space-y-6">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard
        label="Revenue"
        periodLabel={comparison?.current.period_label}
        currentValue={comparison ? money(comparison.current.revenue) : money(data.total_revenue)}
        allTimeValue={money(data.total_revenue)}
        delta={comparison?.revenue_delta_pct}
        priorPeriodLabel={comparison?.prior.period_label}
      />
      <KpiCard
        label="Expenses"
        periodLabel={comparison?.current.period_label}
        currentValue={comparison ? money(comparison.current.expenses) : money(data.total_expenses)}
        allTimeValue={money(data.total_expenses)}
        delta={comparison?.expense_delta_pct}
        priorPeriodLabel={comparison?.prior.period_label}
        invertDelta
      />
      <KpiCard
        label="Profit"
        periodLabel={comparison?.current.period_label}
        currentValue={comparison ? money(comparison.current.net_profit) : money(data.net_profit)}
        allTimeValue={money(data.net_profit)}
        delta={comparison?.profit_delta_pct}
        priorPeriodLabel={comparison?.prior.period_label}
      />
      <KpiCard
        label="Average order value"
        periodLabel={comparison?.current.period_label}
        currentValue={comparison ? money(comparison.current.average_order_value) : money(data.average_order_value)}
        allTimeValue={money(data.average_order_value)}
        delta={comparison?.aov_delta_pct}
        priorPeriodLabel={comparison?.prior.period_label}
      />
    </div>

    <ChartCard
      title="Revenue over time"
      takeaway={data.revenue_trend.length ? "This chart shows the revenue recorded in your imported sales files, grouped by backend service." : "Import sales data to see your revenue over time."}
      details={trendData}
    >
      <div className="mb-4 flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800">
        {(["daily", "weekly", "monthly"] as Granularity[]).map((option) => (
          <button
            key={option}
            onClick={() => setGranularity(option)}
            className={cn("rounded-lg px-3 py-1.5 text-sm font-medium capitalize", granularity === option ? "bg-surface text-ink shadow-sm" : "text-muted")}
          >
            {option}
          </button>
        ))}
      </div>
      {trendQuery.isPending ? (
        <div className="flex h-[260px] items-center justify-center text-muted">
          <LoaderCircle className="animate-spin" size={20} />
          <span className="ml-2 text-sm">Loading trend data…</span>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={trendData}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" />
            <XAxis dataKey="label" tickLine={false} axisLine={false} />
            <YAxis tickFormatter={money} tickLine={false} axisLine={false} width={76} />
            <Tooltip formatter={(value) => money(Number(value))} />
            <Line type="monotone" dataKey="revenue" name="Revenue" stroke="#2563eb" strokeWidth={3} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ChartCard>

    <div className="grid gap-6 lg:grid-cols-2">
      <ChartCard title="Top products" takeaway={data.top_products[0] ? `${data.top_products[0].product} is your highest-revenue product in the imported data.` : "Import sales data to see your top products."} details={data.top_products}>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data.top_products} layout="vertical" margin={{ left: 24 }}>
            <XAxis type="number" tickFormatter={money} hide />
            <YAxis type="category" dataKey="product" width={105} tickLine={false} axisLine={false} />
            <Tooltip formatter={(value) => money(Number(value))} />
            <Bar dataKey="revenue" name="Revenue" fill="#2563eb" radius={[0, 6, 6, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
      <ChartCard title="Where money was spent" takeaway={data.expense_breakdown[0] ? `${data.expense_breakdown[0].category} is the largest expense group in the imported data.` : "Import expense data to see where money was spent."} details={data.expense_breakdown}>
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie data={data.expense_breakdown} dataKey="amount" nameKey="category" innerRadius={58} outerRadius={92} paddingAngle={3}>
              {data.expense_breakdown.map((entry, index) => <Cell key={entry.category} fill={palette[index % palette.length]} />)}
            </Pie>
            <Tooltip formatter={(value) => money(Number(value))} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  </div>;
}

function Compare({ comparison, loading, error }: { comparison: PeriodComparison | null; loading: boolean; error: Error | null }) {
  if (loading) return <PanelLoading />;
  if (error) return <PageError error={error} />;
  if (!comparison) return <NoData text="Import at least two months of data to compare them here." />;
  const rows = [
    { label: "Revenue", current: comparison.current.revenue, prior: comparison.prior.revenue, delta: comparison.revenue_delta, percent: comparison.revenue_delta_pct, invert: false },
    { label: "Expenses", current: comparison.current.expenses, prior: comparison.prior.expenses, delta: comparison.expense_delta, percent: comparison.expense_delta_pct, invert: true },
    { label: "Profit", current: comparison.current.net_profit, prior: comparison.prior.net_profit, delta: comparison.profit_delta, percent: comparison.profit_delta_pct, invert: false },
    { label: "Average order value", current: comparison.current.average_order_value, prior: comparison.prior.average_order_value, delta: comparison.aov_delta, percent: comparison.aov_delta_pct, invert: false },
  ];
  return <div className="space-y-6">
    <Card className="p-6">
      <p className="text-sm text-muted">Comparing</p>
      <h2 className="mt-1 text-xl font-bold">{comparison.current.period_label} and {comparison.prior.period_label}</h2>
      <div className="mt-5 overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b text-muted">
            <tr>
              <th className="px-2 py-3">Metric</th>
              <th className="px-2 py-3">Current</th>
              <th className="px-2 py-3">Earlier</th>
              <th className="px-2 py-3">Change</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-b">
                <td className="px-2 py-3 font-semibold">{row.label}</td>
                <td className="px-2 py-3">{money(row.current)}</td>
                <td className="px-2 py-3">{money(row.prior)}</td>
                <td className="px-2 py-3">
                  <Delta value={row.percent} invert={row.invert} /> <span className="ml-1 text-muted">{money(row.delta)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-sm text-muted">Profit changed by {money(comparison.profit_delta)} between these two months.</p>
      <Details rows={comparison.product_shifts} />
    </Card>
  </div>;
}

function Unusual({ report, loading, error }: { report: { total_anomalies: number; revenue_anomalies: Anomaly[]; expense_anomalies: Anomaly[] } | null; loading: boolean; error: Error | null }) {
  if (loading) return <PanelLoading />;
  if (error) return <PageError error={error} />;
  if (!report || report.total_anomalies === 0) return <NoData text="No unusual activity was found in the imported data." />;
  const items = [...report.revenue_anomalies, ...report.expense_anomalies];
  return <Card className="p-6"><p className="text-sm text-muted">Unusual activity found</p><h2 className="mt-1 text-xl font-bold">{report.total_anomalies} days worth a closer look</h2><p className="mt-3 text-sm text-muted">These are days that differ noticeably from the usual pattern in your data.</p><div className="mt-6 space-y-3">{items.map((item) => <article key={`${item.metric}-${item.date}-${item.description}`} className="rounded-xl border p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-semibold">{plainDate(item.date)} · {item.metric === "revenue" ? "Revenue" : "Expenses"}</p><p className="mt-1 text-sm text-muted">{item.description}</p></div><Severity severity={item.severity} /></div><div className="mt-3 grid gap-2 text-sm text-muted sm:grid-cols-3"><span>Actual: <strong className="text-ink">{money(item.actual_value)}</strong></span><span>Usual: <strong className="text-ink">{money(item.expected_value)}</strong></span><span>Difference: <strong className="text-ink">{signedPercent(item.deviation_pct)}</strong></span></div></article>)}</div><Details rows={items as unknown as Array<Record<string, unknown>>} /></Card>;
}

function Diagnosis({ diagnosis, loading, error }: { diagnosis: ProfitDiagnosis | null; loading: boolean; error: Error | null }) {
  if (loading) return <PanelLoading />;
  if (error) return <PageError error={error} />;
  if (!diagnosis) return <NoData text="Import at least two months of data to understand why profit changed." />;
  return <div className="space-y-6"><Card className="p-6"><p className="text-sm text-muted">Main reason profit changed</p><h2 className="mt-1 text-xl font-bold">{diagnosis.primary_driver}</h2><p className="mt-3 text-muted">Profit changed by {money(diagnosis.profit_change)} from {diagnosis.comparison_label} to {diagnosis.period_label}.</p>{diagnosis.key_insights.length > 0 && <ul className="mt-5 space-y-2 text-sm text-muted">{diagnosis.key_insights.map((insight) => <li key={insight}>• {insight}</li>)}</ul>}</Card><ChartCard title="How profit moved" takeaway={diagnosis.primary_driver} details={diagnosis.waterfall_df}><ResponsiveContainer width="100%" height={280}><BarChart data={diagnosis.waterfall_df}><CartesianGrid vertical={false} strokeDasharray="3 3" /><XAxis dataKey="label" tickLine={false} axisLine={false} /><YAxis tickFormatter={money} tickLine={false} axisLine={false} width={80} /><Tooltip formatter={(value) => money(Number(value))} /><Bar dataKey="value" name="Profit movement" radius={[6, 6, 0, 0]}>{diagnosis.waterfall_df.map((item) => <Cell key={item.label} fill={item.value < 0 ? "#e11d48" : "#059669"} />)}</Bar></BarChart></ResponsiveContainer></ChartCard>{diagnosis.recommendations.length > 0 && <Card className="p-6"><h3 className="font-semibold">Next steps to consider</h3><ul className="mt-4 space-y-2 text-sm leading-6 text-muted">{diagnosis.recommendations.map((item) => <li key={item}>• {item}</li>)}</ul><Details rows={diagnosis.top_expense_surges.concat(diagnosis.top_revenue_drags)} /></Card>}</div>;
}

function KpiCard({
  label,
  periodLabel,
  currentValue,
  allTimeValue,
  delta,
  priorPeriodLabel,
  invertDelta = false,
}: {
  label: string;
  periodLabel?: string;
  currentValue: string;
  allTimeValue: string;
  delta?: number;
  priorPeriodLabel?: string;
  invertDelta?: boolean;
}) {
  return (
    <Card className="flex flex-col justify-between p-5">
      <div>
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium text-muted">{label}</p>
          {periodLabel ? (
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-muted dark:bg-slate-800">
              {periodLabel}
            </span>
          ) : (
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-muted dark:bg-slate-800">
              All time
            </span>
          )}
        </div>
        <p className="mt-2 text-2xl font-bold tracking-tight">{currentValue}</p>
        {delta === undefined ? (
          <p className="mt-2 text-xs text-muted">No earlier month to compare yet.</p>
        ) : (
          <p className="mt-2 text-xs">
            <Delta value={delta} invert={invertDelta} />
            <span className="ml-1 text-muted">vs {priorPeriodLabel ?? "earlier month"}</span>
          </p>
        )}
      </div>
      <div className="mt-4 border-t pt-3 text-xs text-muted">
        <span>All time: </span>
        <strong className="font-semibold text-ink">{allTimeValue}</strong>
      </div>
    </Card>
  );
}

function Delta({ value, invert = false }: { value: number; invert?: boolean }) {
  const isPositive = value > 0;
  const isNegative = value < 0;
  const isGood = invert ? isNegative : isPositive;
  const isBad = invert ? isPositive : isNegative;
  const Icon = isPositive ? ArrowUpRight : isNegative ? ArrowDownRight : ArrowRight;
  const color = isGood ? "text-emerald-600" : isBad ? "text-rose-600" : "text-muted";
  return (
    <span className={cn("inline-flex items-center gap-1 font-semibold", color)}>
      <Icon size={14} />
      {signedPercent(value)}
    </span>
  );
}

function Severity({ severity }: { severity: "critical" | "warning" | "info" }) { const styles = { critical: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200", warning: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200", info: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200" }; return <span className={cn("rounded-full px-3 py-1 text-xs font-bold capitalize", styles[severity])}>{severity}</span>; }
function ChartCard({ title, takeaway, details, children }: { title: string; takeaway: string; details: Array<Record<string, unknown>> | Array<{ label: string; value: number }> | Array<{ date: string; revenue: number }>; children: React.ReactNode }) { return <Card className="p-5 sm:p-6"><h2 className="text-lg font-bold">{title}</h2><div className="mt-5">{children}</div><p className="mt-4 text-sm leading-6 text-muted">{takeaway}</p><Details rows={details as Array<Record<string, unknown>>} /></Card>; }
function Details({ rows }: { rows: Array<Record<string, unknown>> }) { if (rows.length === 0) return null; const columns = Object.keys(rows[0]); return <details className="mt-5 rounded-xl border p-3"><summary className="cursor-pointer text-sm font-semibold">Show details</summary><div className="mt-3 overflow-x-auto"><table className="min-w-full text-left text-xs"><thead className="text-muted"><tr>{columns.map((column) => <th key={column} className="px-2 py-2">{column.replace(/_/g, " ")}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index} className="border-t">{columns.map((column) => <td key={column} className="px-2 py-2">{String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table></div></details>; }
function PageLoading() { return <div className="grid min-h-64 place-items-center text-muted"><span className="inline-flex items-center gap-2"><LoaderCircle className="animate-spin" size={19} /> Loading your business data…</span></div>; }
function PanelLoading() { return <Card className="grid min-h-52 place-items-center p-6 text-muted"><span className="inline-flex items-center gap-2"><LoaderCircle className="animate-spin" size={19} /> Looking at your data…</span></Card>; }
function PageError({ error, retry }: { error: Error; retry?: () => void }) { const message = error instanceof ApiError ? error.message : "We could not load this information."; return <Card className="mx-auto mt-7 max-w-xl p-6 text-center"><AlertCircle className="mx-auto text-rose-600" /><h2 className="mt-3 font-bold">We could not load this page</h2><p className="mt-2 text-sm text-muted">{message}</p>{retry && <Button className="mt-5" variant="outline" onClick={retry}>Try again</Button>}</Card>; }
function EmptyDashboard() { return <Card className="mx-auto mt-7 max-w-2xl p-8 text-center"><BarChart3 className="mx-auto text-brand" size={30} /><h2 className="mt-4 text-xl font-bold">Your dashboard will appear here.</h2><p className="mt-2 text-muted">Upload a sales or expense file to start seeing your business information.</p><Button className="mt-6" asChild><a href="/upload">Upload files</a></Button></Card>; }
function NoData({ text }: { text: string }) { return <Card className="p-8 text-center text-muted">{text}</Card>; }

