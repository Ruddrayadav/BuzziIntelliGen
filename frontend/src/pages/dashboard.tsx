import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Calendar,
  CheckCircle2,
  Clock,
  FileText,
  Info,
  Layers,
  LoaderCircle,
  Package,
  Pencil,
  ReceiptText,
  ShoppingBag,
  Sparkles,
  Target,
  Trash2,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  api,
  ApiError,
  type Anomaly,
  type AttentionItem,
  type DashboardData,
  type DayOfWeekDay,
  type DayOfWeekInsight,
  type PeriodComparison,
  type ProfitDiagnosis,
  type SlowMoverItem,
  type TargetPacing,
} from "@/lib/api";
import { money, plainDate, signedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tab = "overview" | "compare" | "unusual" | "diagnosis";
type Granularity = "daily" | "weekly" | "monthly";
type ProductViewMode = "revenue" | "units_top" | "units_bottom";

const tabs: Array<{ value: Tab; label: string }> = [
  { value: "overview", label: "Overview" },
  { value: "compare", label: "Compare months" },
  { value: "unusual", label: "Unusual activity" },
  { value: "diagnosis", label: "Why profit changed" },
];

const palette = ["#2563eb", "#60a5fa", "#a78bfa", "#34d399", "#fbbf24", "#fb7185", "#38bdf8", "#818cf8"];

export function DashboardPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [granularity, setGranularity] = useState<Granularity>("daily");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  const dashboard = useQuery({
    queryKey: ["dashboard", startDate, endDate],
    queryFn: () => api.dashboard(startDate || undefined, endDate || undefined),
  });
  const comparison = useQuery({ queryKey: ["analytics", "compare"], queryFn: () => api.compare() });
  const anomalies = useQuery({ queryKey: ["analytics", "anomalies"], queryFn: api.anomalies });
  const diagnosis = useQuery({ queryKey: ["analytics", "diagnosis"], queryFn: () => api.diagnosis() });

  if (dashboard.isPending) return <PageLoading />;
  if (dashboard.isError) return <PageError error={dashboard.error} retry={() => void dashboard.refetch()} />;
  const data = dashboard.data;
  const isEmpty = data.revenue_trend.length === 0 && data.expense_breakdown.length === 0;

  const handleExportPdf = async () => {
    setIsExportingPdf(true);
    setPdfError(null);
    try {
      let targetMonth: string | undefined = undefined;
      if (startDate && startDate.length >= 7) {
        targetMonth = startDate.slice(0, 7);
      }
      await api.downloadMonthlyPdf(targetMonth);
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : "Failed to download PDF report");
    } finally {
      setIsExportingPdf(false);
    }
  };

  const handleAttentionNavigate = (targetTab: string) => {
    const mappedTab: Tab =
      targetTab === "diagnostics"
        ? "diagnosis"
        : targetTab === "comparison"
        ? "compare"
        : targetTab === "anomalies"
        ? "unusual"
        : "overview";
    setTab(mappedTab);
  };

  return (
    <section>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">Business dashboard</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">A clear view of your business.</h1>
          <p className="mt-2 text-muted">The numbers below come directly from the files you imported.</p>
        </div>

        {/* Action Controls: Date Range Filter & PDF Export Button */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-surface p-2 text-xs">
            <Calendar size={14} className="text-muted ml-1" />
            <div className="flex items-center gap-1.5">
              <label htmlFor="filter-start" className="text-muted">From</label>
              <input
                id="filter-start"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="rounded-lg border bg-background px-2 py-1 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </div>
            <div className="flex items-center gap-1.5">
              <label htmlFor="filter-end" className="text-muted">To</label>
              <input
                id="filter-end"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="rounded-lg border bg-background px-2 py-1 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </div>
            {(startDate || endDate) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setStartDate("");
                  setEndDate("");
                }}
                className="h-7 px-2 text-xs text-muted hover:text-ink"
              >
                <X size={13} className="mr-1" /> Reset
              </Button>
            )}
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleExportPdf}
            disabled={isExportingPdf || isEmpty}
            className="h-10 gap-1.5 rounded-xl border bg-surface px-3 text-xs font-semibold hover:bg-surface-hover"
            title="Download executive monthly PDF report"
          >
            {isExportingPdf ? (
              <>
                <LoaderCircle size={14} className="animate-spin text-brand" />
                <span>Generating PDF...</span>
              </>
            ) : (
              <>
                <FileText size={14} className="text-brand" />
                <span>Export Report (PDF)</span>
              </>
            )}
          </Button>
        </div>
      </div>

      {pdfError && (
        <div className="mt-3 flex items-center justify-between rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
          <span>{pdfError}</span>
          <button onClick={() => setPdfError(null)} className="text-rose-600 hover:text-rose-800">
            <X size={14} />
          </button>
        </div>
      )}


      {/* "What Needs Your Attention" Panel */}
      {data.attention_items && data.attention_items.length > 0 && !isEmpty && (
        <AttentionPanel
          items={data.attention_items}
          onNavigate={handleAttentionNavigate}
        />
      )}

      <div className="mt-6 flex gap-2 overflow-x-auto border-b" role="tablist" aria-label="Dashboard sections">
        {tabs.map((item) => (
          <button
            key={item.value}
            role="tab"
            aria-selected={tab === item.value}
            onClick={() => setTab(item.value)}
            className={cn(
              "shrink-0 border-b-2 px-3 py-3 text-sm font-semibold transition-colors",
              tab === item.value ? "border-brand text-brand" : "border-transparent text-muted hover:text-ink"
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {isEmpty ? (
        <EmptyDashboard />
      ) : (
        <div className="mt-7">
          {tab === "overview" && (
            <Overview
              data={data}
              comparison={comparison.data ?? null}
              granularity={granularity}
              setGranularity={setGranularity}
              startDate={startDate}
              endDate={endDate}
            />
          )}
          {tab === "compare" && <Compare comparison={comparison.data ?? null} loading={comparison.isPending} error={comparison.error} />}
          {tab === "unusual" && <Unusual report={anomalies.data ?? null} loading={anomalies.isPending} error={anomalies.error} />}
          {tab === "diagnosis" && <Diagnosis diagnosis={diagnosis.data ?? null} loading={diagnosis.isPending} error={diagnosis.error} />}
        </div>
      )}
    </section>
  );
}

function Overview({
  data,
  comparison,
  granularity,
  setGranularity,
  startDate,
  endDate,
}: {
  data: DashboardData;
  comparison: PeriodComparison | null;
  granularity: Granularity;
  setGranularity: (value: Granularity) => void;
  startDate: string;
  endDate: string;
}) {
  const [productMode, setProductMode] = useState<ProductViewMode>("revenue");

  const trendQuery = useQuery({
    queryKey: ["dashboard", "trend", granularity, startDate, endDate],
    queryFn: () => api.trend(granularity, startDate || undefined, endDate || undefined),
  });
  const trendData = trendQuery.data ?? [];

  // Active product dataset based on view mode
  const activeProducts = useMemo(() => {
    if (productMode === "units_top") return data.top_products_by_qty;
    if (productMode === "units_bottom") return data.bottom_products_by_qty;
    return data.top_products;
  }, [productMode, data]);

  const productTakeaway = useMemo(() => {
    if (productMode === "revenue") {
      return data.takeaways?.top_products ?? "Top products by revenue.";
    }
    return data.takeaways?.product_volume ?? "Products ranked by units sold.";
  }, [productMode, data]);

  return (
    <div className="space-y-6">
      {/* KPI Cards Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
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
          label="Avg order value"
          periodLabel={comparison?.current.period_label}
          currentValue={comparison ? money(comparison.current.average_order_value) : money(data.average_order_value)}
          allTimeValue={money(data.average_order_value)}
          delta={comparison?.aov_delta_pct}
          priorPeriodLabel={comparison?.prior.period_label}
        />
        <SimpleKpiCard
          label="Transactions"
          value={data.total_transactions.toLocaleString("en-IN")}
          icon={<ReceiptText size={17} className="text-brand" />}
          subtitle="Total unique orders recorded"
        />
        <SimpleKpiCard
          label="Units sold"
          value={data.total_units_sold.toLocaleString("en-IN")}
          icon={<Package size={17} className="text-brand" />}
          subtitle="Cumulative items purchased"
        />
      </div>

      {/* Target Pacing Card */}
      <TargetPacingCard pacing={data.target_pacing} />

      {/* Financial Trend: Revenue & Expenses over time */}
      <ChartCard
        title="Revenue & Expense trend"
        takeaway={data.takeaways?.revenue_trend ?? "Revenue and operational costs tracked over time."}
        details={trendData}
      >
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800">
            {(["daily", "weekly", "monthly"] as Granularity[]).map((option) => (
              <button
                key={option}
                onClick={() => setGranularity(option)}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-xs font-semibold capitalize transition-all",
                  granularity === option ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
                )}
              >
                {option}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-4 text-xs font-medium">
            <span className="flex items-center gap-1.5 text-blue-600 dark:text-blue-400">
              <span className="h-2.5 w-2.5 rounded-full bg-blue-600" /> Revenue
            </span>
            <span className="flex items-center gap-1.5 text-rose-500">
              <span className="h-2.5 w-2.5 rounded-full bg-rose-500" /> Expenses
            </span>
          </div>
        </div>

        {trendQuery.isPending ? (
          <div className="flex h-[260px] items-center justify-center text-muted">
            <LoaderCircle className="animate-spin" size={20} />
            <span className="ml-2 text-sm">Loading financial series…</span>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trendData}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" opacity={0.5} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={money} tickLine={false} axisLine={false} width={76} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value, name) => [money(Number(value)), name === "revenue" ? "Revenue" : "Expenses"]} />
              <Line type="monotone" dataKey="revenue" name="revenue" stroke="#2563eb" strokeWidth={2.5} dot={false} />
              <Line type="monotone" dataKey="expenses" name="expenses" stroke="#e11d48" strokeWidth={2} strokeDasharray="4 4" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </ChartCard>

      {/* Row 2: Category Performance & Expense Breakdown */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Category Performance */}
        <ChartCard
          title="Category performance"
          takeaway={data.takeaways?.category_performance ?? "Revenue distribution across product categories."}
          details={data.category_performance}
        >
          {data.category_performance.length === 0 ? (
            <div className="flex h-[240px] items-center justify-center text-sm text-muted">
              No category data recorded in sales files.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.category_performance} layout="vertical" margin={{ left: 16, right: 16 }}>
                <CartesianGrid horizontal={false} strokeDasharray="3 3" opacity={0.4} />
                <XAxis type="number" tickFormatter={money} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="category" width={110} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value) => [money(Number(value)), "Revenue"]} />
                <Bar dataKey="revenue" name="Revenue" fill="#3b82f6" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        {/* Expense Breakdown */}
        <ChartCard
          title="Where money was spent"
          takeaway={data.takeaways?.expense_breakdown ?? "Breakdown of operating costs by category."}
          details={data.expense_breakdown}
        >
          {data.expense_breakdown.length === 0 ? (
            <div className="flex h-[240px] items-center justify-center text-sm text-muted">
              No expense records found.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={data.expense_breakdown}
                  dataKey="amount"
                  nameKey="category"
                  innerRadius={55}
                  outerRadius={88}
                  paddingAngle={3}
                >
                  {data.expense_breakdown.map((entry, index) => (
                    <Cell key={entry.category} fill={palette[index % palette.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => [money(Number(value)), "Amount"]} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      {/* Row 3: Product Highlights (Revenue vs Volume Tabs) */}
      <ChartCard
        title="Product insights"
        takeaway={productTakeaway}
        details={activeProducts}
      >
        <div className="mb-4 flex flex-wrap gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800 w-fit">
          <button
            onClick={() => setProductMode("revenue")}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
              productMode === "revenue" ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
            )}
          >
            Top earners (Revenue)
          </button>
          <button
            onClick={() => setProductMode("units_top")}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
              productMode === "units_top" ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
            )}
          >
            Most sold (Units)
          </button>
          <button
            onClick={() => setProductMode("units_bottom")}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
              productMode === "units_bottom" ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
            )}
          >
            Lowest volume (Units)
          </button>
        </div>

        {activeProducts.length === 0 ? (
          <div className="flex h-[230px] items-center justify-center text-sm text-muted">
            No product records found.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={activeProducts} layout="vertical" margin={{ left: 24, right: 16 }}>
              <CartesianGrid horizontal={false} strokeDasharray="3 3" opacity={0.4} />
              <XAxis
                type="number"
                tickFormatter={productMode === "revenue" ? money : (v) => `${v} pcs`}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11 }}
              />
              <YAxis type="category" dataKey="product" width={120} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(val, name) => [
                  name === "quantity" ? `${val} units` : money(Number(val)),
                  name === "quantity" ? "Units Sold" : "Revenue",
                ]}
              />
              <Bar
                dataKey={productMode === "revenue" ? "revenue" : "quantity"}
                name={productMode === "revenue" ? "revenue" : "quantity"}
                fill={productMode === "units_bottom" ? "#f59e0b" : "#2563eb"}
                radius={[0, 6, 6, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </ChartCard>

      {/* Row 4: Day-of-Week Intelligence */}
      <DayOfWeekCard insight={data.day_of_week_insight} />

      {/* Row 5: Slow-Movers List */}
      <SlowMoversCard items={data.slow_movers} />
    </div>
  );
}

function Compare({
  comparison,
  loading,
  error,
}: {
  comparison: PeriodComparison | null;
  loading: boolean;
  error: Error | null;
}) {
  if (loading) return <PanelLoading />;
  if (error) return <PageError error={error} />;
  if (!comparison) return <NoData text="Import at least two months of data to compare them here." />;

  const rows = [
    { label: "Revenue", current: comparison.current.revenue, prior: comparison.prior.revenue, delta: comparison.revenue_delta, percent: comparison.revenue_delta_pct, invert: false },
    { label: "Expenses", current: comparison.current.expenses, prior: comparison.prior.expenses, delta: comparison.expense_delta, percent: comparison.expense_delta_pct, invert: true },
    { label: "Profit", current: comparison.current.net_profit, prior: comparison.prior.net_profit, delta: comparison.profit_delta, percent: comparison.profit_delta_pct, invert: false },
    { label: "Average order value", current: comparison.current.average_order_value, prior: comparison.prior.average_order_value, delta: comparison.aov_delta, percent: comparison.aov_delta_pct, invert: false },
  ];

  // Combined shifts for chart
  const gainerDeclinerData = useMemo(() => {
    const list: Array<{ product: string; delta: number; type: "gainer" | "decliner" }> = [];
    (comparison.top_gainers || []).forEach((g) => {
      list.push({ product: String(g.product), delta: Number(g.delta), type: "gainer" });
    });
    (comparison.top_decliners || []).forEach((d) => {
      list.push({ product: String(d.product), delta: Number(d.delta), type: "decliner" });
    });
    return list;
  }, [comparison]);

  const topGainer = comparison.top_gainers?.[0];
  const topDecliner = comparison.top_decliners?.[0];
  const gainerTakeaway = topGainer && topDecliner
    ? `'${topGainer.product}' grew the most (+₹${Number(topGainer.delta).toLocaleString("en-IN")}), while '${topDecliner.product}' had the largest sales drop (-₹${Math.abs(Number(topDecliner.delta)).toLocaleString("en-IN")}).`
    : "Product shifts between reporting periods.";

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <p className="text-sm text-muted">Comparing</p>
        <h2 className="mt-1 text-xl font-bold">
          {comparison.current.period_label} and {comparison.prior.period_label}
        </h2>
        <div className="mt-5 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b text-muted">
              <tr>
                <th className="px-2 py-3 font-medium">Metric</th>
                <th className="px-2 py-3 font-medium">Current</th>
                <th className="px-2 py-3 font-medium">Earlier</th>
                <th className="px-2 py-3 font-medium">Change</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label} className="border-b">
                  <td className="px-2 py-3 font-semibold">{row.label}</td>
                  <td className="px-2 py-3">{money(row.current)}</td>
                  <td className="px-2 py-3">{money(row.prior)}</td>
                  <td className="px-2 py-3">
                    <Delta value={row.percent} invert={row.invert} />{" "}
                    <span className="ml-1 text-muted">({money(row.delta)})</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-sm text-muted">
          Profit changed by <strong className="text-ink">{money(comparison.profit_delta)}</strong> between these two periods.
        </p>
      </Card>

      {/* Top Gainers & Decliners Chart */}
      {gainerDeclinerData.length > 0 && (
        <ChartCard
          title="Top product gainers and decliners"
          takeaway={gainerTakeaway}
          details={gainerDeclinerData}
        >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={gainerDeclinerData} layout="vertical" margin={{ left: 24, right: 16 }}>
              <CartesianGrid horizontal={false} strokeDasharray="3 3" opacity={0.4} />
              <XAxis type="number" tickFormatter={money} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="product" width={115} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value) => [money(Number(value)), "Revenue Change"]} />
              <Bar dataKey="delta" name="Revenue Change" radius={[0, 4, 4, 0]}>
                {gainerDeclinerData.map((entry) => (
                  <Cell key={entry.product} fill={entry.delta >= 0 ? "#10b981" : "#ef4444"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      <Card className="p-6">
        <h3 className="font-semibold text-base">All product shifts</h3>
        <p className="text-xs text-muted mt-1">Detailed period-over-period variance for all catalog items.</p>
        <Details rows={comparison.product_shifts} />
      </Card>
    </div>
  );
}

function Unusual({
  report,
  loading,
  error,
}: {
  report: { total_anomalies: number; revenue_anomalies: Anomaly[]; expense_anomalies: Anomaly[] } | null;
  loading: boolean;
  error: Error | null;
}) {
  if (loading) return <PanelLoading />;
  if (error) return <PageError error={error} />;
  if (!report || report.total_anomalies === 0) {
    return <NoData text="No unusual activity was found in the imported records." />;
  }
  const items = [...report.revenue_anomalies, ...report.expense_anomalies];

  return (
    <Card className="p-6">
      <p className="text-sm text-muted">Unusual activity found</p>
      <h2 className="mt-1 text-xl font-bold">{report.total_anomalies} days worth a closer look</h2>
      <p className="mt-2 text-sm text-muted">These are days that differ noticeably from your usual operating baseline.</p>

      <div className="mt-6 space-y-4">
        {items.map((item) => (
          <article key={`${item.metric}-${item.date}-${item.description}`} className="rounded-xl border p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-semibold text-sm">
                  {plainDate(item.date)} · {item.metric === "revenue" ? "Revenue" : "Expenses"}
                </p>
                <p className="mt-1 text-sm text-ink">{item.description}</p>
              </div>
              <Severity severity={item.severity} />
            </div>

            <div className="mt-3 grid gap-2 text-xs text-muted sm:grid-cols-3">
              <span>Actual: <strong className="text-ink">{money(item.actual_value)}</strong></span>
              <span>Usual: <strong className="text-ink">{money(item.expected_value)}</strong></span>
              <span>Difference: <strong className="text-ink">{signedPercent(item.deviation_pct)}</strong></span>
            </div>

            {/* Detailed expense item descriptions */}
            {item.expense_details && item.expense_details.length > 0 && (
              <div className="mt-3 rounded-lg border bg-slate-50 p-2.5 dark:bg-slate-900/50">
                <p className="text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
                  Expense Line Items on this day:
                </p>
                <div className="space-y-1">
                  {item.expense_details.map((exp, idx) => (
                    <div key={idx} className="flex items-center justify-between text-xs text-muted">
                      <span>
                        <strong className="text-ink">{exp.category}</strong>
                        {exp.description ? ` — ${exp.description}` : ""}
                      </span>
                      <span className="font-medium text-ink">{money(exp.amount)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </article>
        ))}
      </div>
      <Details rows={items as unknown as Array<Record<string, unknown>>} />
    </Card>
  );
}

function Diagnosis({
  diagnosis,
  loading,
  error,
}: {
  diagnosis: ProfitDiagnosis | null;
  loading: boolean;
  error: Error | null;
}) {
  if (loading) return <PanelLoading />;
  if (error) return <PageError error={error} />;
  if (!diagnosis) return <NoData text="Import at least two months of data to understand why profit changed." />;

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <p className="text-sm text-muted">Main reason profit changed</p>
        <h2 className="mt-1 text-xl font-bold">{diagnosis.primary_driver}</h2>
        <p className="mt-3 text-muted">
          Profit changed by {money(diagnosis.profit_change)} from {diagnosis.comparison_label} to {diagnosis.period_label}.
        </p>
        {diagnosis.key_insights.length > 0 && (
          <ul className="mt-5 space-y-2 text-sm text-muted">
            {diagnosis.key_insights.map((insight) => (
              <li key={insight}>• {insight}</li>
            ))}
          </ul>
        )}
      </Card>

      <ChartCard title="How profit moved" takeaway={diagnosis.primary_driver} details={diagnosis.waterfall_df}>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={diagnosis.waterfall_df}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" opacity={0.5} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={money} tickLine={false} axisLine={false} width={80} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(value) => money(Number(value))} />
            <Bar dataKey="value" name="Profit movement" radius={[6, 6, 0, 0]}>
              {diagnosis.waterfall_df.map((item) => (
                <Cell key={item.label} fill={item.value < 0 ? "#e11d48" : "#059669"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      {diagnosis.recommendations.length > 0 && (
        <Card className="p-6">
          <h3 className="font-semibold">Next steps to consider</h3>
          <ul className="mt-4 space-y-2 text-sm leading-6 text-muted">
            {diagnosis.recommendations.map((item) => (
              <li key={item}>• {item}</li>
            ))}
          </ul>
          <Details rows={diagnosis.top_expense_surges.concat(diagnosis.top_revenue_drags)} />
        </Card>
      )}
    </div>
  );
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
    <Card className="flex flex-col justify-between p-4 sm:p-5">
      <div>
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold text-muted uppercase tracking-wider">{label}</p>
          {periodLabel ? (
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-muted dark:bg-slate-800">
              {periodLabel}
            </span>
          ) : (
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-muted dark:bg-slate-800">
              Filtered
            </span>
          )}
        </div>
        <p className="mt-2 text-2xl font-bold tracking-tight">{currentValue}</p>
        {delta === undefined ? (
          <p className="mt-2 text-xs text-muted">No earlier month to compare.</p>
        ) : (
          <p className="mt-2 text-xs">
            <Delta value={delta} invert={invertDelta} />
            <span className="ml-1 text-muted">vs {priorPeriodLabel ?? "earlier"}</span>
          </p>
        )}
      </div>
      <div className="mt-4 border-t pt-2.5 text-xs text-muted">
        <span>All time: </span>
        <strong className="font-semibold text-ink">{allTimeValue}</strong>
      </div>
    </Card>
  );
}

function SimpleKpiCard({
  label,
  value,
  icon,
  subtitle,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  subtitle: string;
}) {
  return (
    <Card className="flex flex-col justify-between p-4 sm:p-5">
      <div>
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold text-muted uppercase tracking-wider">{label}</p>
          <span className="rounded-lg bg-blue-50 p-1 dark:bg-blue-950/60">{icon}</span>
        </div>
        <p className="mt-2 text-2xl font-bold tracking-tight">{value}</p>
      </div>
      <div className="mt-4 border-t pt-2.5 text-xs text-muted">
        <span>{subtitle}</span>
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

function Severity({ severity }: { severity: "critical" | "warning" | "info" }) {
  const styles = {
    critical: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
    warning: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
    info: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  };
  return <span className={cn("rounded-full px-3 py-0.5 text-xs font-bold capitalize", styles[severity])}>{severity}</span>;
}

function ChartCard({
  title,
  takeaway,
  details,
  children,
}: {
  title: string;
  takeaway: string;
  details: unknown;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-5 sm:p-6">
      <h2 className="text-base font-bold tracking-tight">{title}</h2>
      <div className="mt-4">{children}</div>
      <div className="mt-4 rounded-xl bg-slate-50 p-3 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-800">
        <p className="text-xs font-medium text-ink leading-relaxed">
          <span className="font-bold text-brand mr-1">Takeaway:</span> {takeaway}
        </p>
      </div>
      <Details rows={Array.isArray(details) ? (details as Array<Record<string, unknown>>) : []} />
    </Card>
  );
}

function Details({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows || rows.length === 0) return null;
  const firstRow = rows[0];
  if (!firstRow || typeof firstRow !== "object") return null;
  const columns = Object.keys(firstRow);
  return (
    <details className="mt-4 rounded-xl border p-3">
      <summary className="cursor-pointer text-xs font-semibold text-muted hover:text-ink">Show data table ({rows.length} rows)</summary>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="text-muted border-b">
            <tr>
              {columns.map((column) => (
                <th key={column} className="px-2 py-2 font-medium">{column.replace(/_/g, " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-t border-slate-100 dark:border-slate-800">
                {columns.map((column) => (
                  <td key={column} className="px-2 py-1.5">{String(row[column] ?? "—")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function PageLoading() {
  return (
    <div className="grid min-h-64 place-items-center text-muted">
      <span className="inline-flex items-center gap-2">
        <LoaderCircle className="animate-spin" size={19} /> Loading your business data…
      </span>
    </div>
  );
}

function PanelLoading() {
  return (
    <Card className="grid min-h-52 place-items-center p-6 text-muted">
      <span className="inline-flex items-center gap-2">
        <LoaderCircle className="animate-spin" size={19} /> Looking at your data…
      </span>
    </Card>
  );
}

function PageError({ error, retry }: { error: Error; retry?: () => void }) {
  const message = error instanceof ApiError ? error.message : "We could not load this information.";
  return (
    <Card className="mx-auto mt-7 max-w-xl p-6 text-center">
      <AlertCircle className="mx-auto text-rose-600" />
      <h2 className="mt-3 font-bold">We could not load this page</h2>
      <p className="mt-2 text-sm text-muted">{message}</p>
      {retry && (
        <Button className="mt-5" variant="outline" onClick={retry}>
          Try again
        </Button>
      )}
    </Card>
  );
}

function EmptyDashboard() {
  return (
    <Card className="mx-auto mt-7 max-w-2xl p-8 text-center">
      <BarChart3 className="mx-auto text-brand" size={30} />
      <h2 className="mt-4 text-xl font-bold">Your dashboard will appear here.</h2>
      <p className="mt-2 text-muted">Upload a sales or expense file to start seeing your business information.</p>
      <Button className="mt-6" asChild>
        <a href="/upload">Upload files</a>
      </Button>
    </Card>
  );
}

function NoData({ text }: { text: string }) {
  return <Card className="p-8 text-center text-muted">{text}</Card>;
}

function AttentionPanel({
  items,
  onNavigate,
}: {
  items: AttentionItem[];
  onNavigate: (tab: string) => void;
}) {
  if (!items || items.length === 0) return null;

  const isAllClear = items.length === 1 && items[0].id === "all_clear";

  return (
    <div className="mt-6 rounded-2xl border bg-surface p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3.5">
        <div className="flex items-center gap-2.5">
          <span
            className={cn(
              "grid h-8 w-8 place-items-center rounded-xl",
              isAllClear
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
            )}
          >
            {isAllClear ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
          </span>
          <div>
            <h2 className="text-base font-bold text-ink">What Needs Your Attention</h2>
            <p className="text-xs text-muted">
              {isAllClear
                ? "Automatic health check on your business operations"
                : "Automated business risk signals ranked by financial impact"}
            </p>
          </div>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-muted dark:bg-slate-800">
          {isAllClear ? "All Systems Healthy" : `${items.length} prioritized item${items.length === 1 ? "" : "s"}`}
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => {
          const isCritical = item.severity === "critical";
          const isWarning = item.severity === "warning";

          return (
            <div
              key={item.id}
              className={cn(
                "flex flex-col justify-between rounded-xl border p-4 transition-all hover:shadow-md",
                isCritical
                  ? "border-rose-200 bg-rose-50/50 dark:border-rose-900/40 dark:bg-rose-950/20"
                  : isWarning
                  ? "border-amber-200 bg-amber-50/40 dark:border-amber-900/40 dark:bg-amber-950/20"
                  : "border-blue-200 bg-blue-50/30 dark:border-blue-900/40 dark:bg-blue-950/10"
              )}
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider",
                      isCritical
                        ? "bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-200"
                        : isWarning
                        ? "bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200"
                        : "bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-200"
                    )}
                  >
                    {isCritical ? (
                      <AlertCircle size={12} />
                    ) : isWarning ? (
                      <AlertTriangle size={12} />
                    ) : (
                      <CheckCircle2 size={12} />
                    )}
                    {item.severity}
                  </span>
                </div>

                <h3 className="mt-2 text-sm font-bold leading-snug text-ink">{item.title}</h3>
                <p className="mt-1 text-xs leading-relaxed text-muted">{item.message}</p>
              </div>

              {item.action_tab && item.action_label && item.id !== "all_clear" && (
                <div className="mt-4 border-t border-slate-200/60 pt-2 dark:border-slate-800/60">
                  <button
                    type="button"
                    onClick={() => onNavigate(item.action_tab)}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline"
                  >
                    <span>{item.action_label}</span>
                    <ArrowRight size={13} />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DayOfWeekCard({ insight }: { insight?: DayOfWeekInsight | null }) {
  if (!insight || !insight.days || insight.days.length === 0) return null;

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3.5">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-blue-500/10 text-brand">
            <Clock size={18} />
          </span>
          <div>
            <h2 className="text-base font-bold text-ink">Day-of-Week Sales Performance</h2>
            <p className="text-xs text-muted">
              Analyze daily revenue patterns across Monday–Sunday to optimize staffing and purchasing
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700 dark:bg-blue-950/60 dark:text-blue-300">
            Peak: {insight.best_day}
          </span>
        </div>
      </div>

      {/* Headlines / Takeaways */}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-blue-100 bg-blue-50/50 p-3.5 dark:border-blue-900/40 dark:bg-blue-950/20">
          <p className="text-xs font-semibold uppercase tracking-wider text-blue-700 dark:text-blue-300">
            Peak vs Trough Pattern
          </p>
          <p className="mt-1 text-xs font-medium leading-relaxed text-ink">
            {insight.headline}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5 dark:border-slate-800 dark:bg-slate-900/40">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">
            Weekend vs Weekday Split
          </p>
          <p className="mt-1 text-xs font-medium leading-relaxed text-ink">
            {insight.weekend_headline}
          </p>
        </div>
      </div>

      {/* Bar Chart */}
      <div className="mt-5">
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={insight.days} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" opacity={0.4} />
            <XAxis dataKey="day_name" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={money} tickLine={false} axisLine={false} width={76} tick={{ fontSize: 11 }} />
            <Tooltip
              formatter={(val, _name, item) => {
                const payload = (item as { payload?: DayOfWeekDay }).payload;
                return [
                  `${money(Number(val))} avg (${payload?.order_count ?? 0} orders, ${payload?.share_pct ?? 0}% total share)`,
                  "Daily Average",
                ];
              }}
            />
            <Bar dataKey="avg_revenue" name="Avg Daily Revenue" radius={[6, 6, 0, 0]}>
              {insight.days.map((entry) => {
                const isBest = entry.day_name === insight.best_day;
                const isLowest = entry.day_name === insight.lowest_day;
                return (
                  <Cell
                    key={entry.day_name}
                    fill={isBest ? "#2563eb" : isLowest ? "#94a3b8" : "#60a5fa"}
                  />
                );
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <Details
        rows={insight.days.map((d) => ({
          day: d.day_name,
          avg_daily_revenue: money(d.avg_revenue),
          total_revenue: money(d.total_revenue),
          order_count: d.order_count,
          share_pct: `${d.share_pct}%`,
        }))}
      />
    </Card>
  );
}

function SlowMoversCard({ items }: { items?: SlowMoverItem[] }) {
  if (!items) return null;

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3.5">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400">
            <ShoppingBag size={18} />
          </span>
          <div>
            <h2 className="text-base font-bold text-ink">Slow-Movers & Stock Velocity</h2>
            <p className="text-xs text-muted">
              Products with sluggish turnover or dormant transactions that may tie up cash
            </p>
          </div>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-muted dark:bg-slate-800">
          {items.length === 0 ? "All items moving well" : `${items.length} item${items.length === 1 ? "" : "s"} flagged`}
        </span>
      </div>

      {items.length === 0 ? (
        <div className="mt-6 flex flex-col items-center justify-center rounded-xl border border-dashed py-8 text-center">
          <CheckCircle2 size={28} className="text-emerald-500" />
          <p className="mt-2 text-sm font-semibold text-ink">Catalog Health Is Strong</p>
          <p className="mt-1 text-xs text-muted">
            All catalog items show healthy sales velocity and recent purchase activity.
          </p>
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="border-b text-muted">
              <tr>
                <th className="px-3 py-2.5 font-semibold">Product</th>
                <th className="px-3 py-2.5 font-semibold">Status</th>
                <th className="px-3 py-2.5 font-semibold">Weekly Velocity</th>
                <th className="px-3 py-2.5 font-semibold">Total Sold</th>
                <th className="px-3 py-2.5 font-semibold">Last Sold</th>
                <th className="px-3 py-2.5 font-semibold">Action Recommendation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {items.map((item) => {
                const statusStyles: Record<string, string> = {
                  Stalled: "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-200",
                  Sluggish: "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-200",
                  "Low Volume": "bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-200",
                  Moderate: "bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-200",
                };

                return (
                  <tr key={item.product} className="hover:bg-slate-50/60 dark:hover:bg-slate-900/40">
                    <td className="px-3 py-2.5 font-semibold text-ink">{item.product}</td>
                    <td className="px-3 py-2.5">
                      <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold", statusStyles[item.status] ?? statusStyles.Moderate)}>
                        {item.status}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-ink font-medium">
                      {item.weekly_velocity} units/wk
                    </td>
                    <td className="px-3 py-2.5 text-muted">
                      <span className="font-medium text-ink">{item.units_sold}</span> units ({money(item.revenue)})
                    </td>
                    <td className="px-3 py-2.5 text-muted">
                      {item.days_since_last_sale === 0 ? "Today" : `${item.days_since_last_sale}d ago`}
                      <span className="block text-[10px] text-muted">{item.last_sold_date}</span>
                    </td>
                    <td className="px-3 py-2.5 text-xs text-muted max-w-xs leading-relaxed">
                      {item.recommendation}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function TargetPacingCard({ pacing }: { pacing?: TargetPacing | null }) {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [targetInput, setTargetInput] = useState(pacing?.target_amount ? String(pacing.target_amount) : "");
  const [errorMsg, setErrorMsg] = useState("");

  const saveMutation = useMutation({
    mutationFn: (amount: number) => {
      const month = pacing?.month ?? new Date().toISOString().slice(0, 7);
      return api.setTarget(month, amount);
    },
    onSuccess: () => {
      setIsEditing(false);
      setErrorMsg("");
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) => {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to save target");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => {
      const month = pacing?.month ?? new Date().toISOString().slice(0, 7);
      return api.deleteTarget(month);
    },
    onSuccess: () => {
      setIsEditing(false);
      setErrorMsg("");
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  if (!pacing) return null;

  const monthLabel = pacing.month_label || pacing.month;

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    const val = parseFloat(targetInput);
    if (isNaN(val) || val <= 0) {
      setErrorMsg("Please enter a valid target amount greater than zero.");
      return;
    }
    saveMutation.mutate(val);
  };

  const statusConfig = {
    achieved: {
      label: "Target Achieved",
      style: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200",
      barColor: "bg-emerald-500",
    },
    ahead: {
      label: `Ahead of Pace (+${pacing.pace_pct}%)`,
      style: "bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-200",
      barColor: "bg-blue-600",
    },
    on_track: {
      label: "On Track",
      style: "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-200",
      barColor: "bg-sky-500",
    },
    behind: {
      label: "Behind Pace",
      style: "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-200",
      barColor: "bg-amber-500",
    },
    none: {
      label: "No Target Set",
      style: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300",
      barColor: "bg-slate-400",
    },
  };

  const currentStatus = statusConfig[pacing.pace_status] || statusConfig.none;
  const progressClamped = Math.min(100, Math.max(0, pacing.progress_pct));
  const expectedPacePct =
    pacing.days_in_month > 0
      ? Math.min(100, Math.max(0, (pacing.days_elapsed / pacing.days_in_month) * 100))
      : 0;

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3.5">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-blue-500/10 text-brand">
            <Target size={18} />
          </span>
          <div>
            <h2 className="text-base font-bold text-ink">Monthly Revenue Target & Pacing</h2>
            <p className="text-xs text-muted">Track run-rate velocity and month-end projections for {monthLabel}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {pacing.has_target && (
            <span className={cn("rounded-full px-2.5 py-1 text-xs font-semibold", currentStatus.style)}>
              {currentStatus.label}
            </span>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setIsEditing(!isEditing);
              setErrorMsg("");
              if (!isEditing && pacing.target_amount) {
                setTargetInput(String(pacing.target_amount));
              }
            }}
            className="h-8 gap-1.5 text-xs"
          >
            <Pencil size={13} />
            {pacing.has_target ? "Change Target" : "Set Target"}
          </Button>
        </div>
      </div>

      {/* Edit Form */}
      {isEditing && (
        <form onSubmit={handleSave} className="mt-4 rounded-xl border bg-slate-50/70 p-4 dark:bg-slate-900/50">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex-1">
              <label htmlFor="target-input" className="block text-xs font-semibold text-ink">
                Revenue Goal for {monthLabel} (₹)
              </label>
              <input
                id="target-input"
                type="number"
                step="100"
                placeholder="e.g. 50000"
                value={targetInput}
                onChange={(e) => setTargetInput(e.target.value)}
                className="mt-1 w-full max-w-xs rounded-lg border bg-surface px-3 py-1.5 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-brand"
                autoFocus
              />
            </div>
            <div className="flex items-center gap-2">
              <Button type="submit" size="sm" disabled={saveMutation.isPending} className="h-8 text-xs">
                {saveMutation.isPending ? "Saving…" : "Save Target"}
              </Button>
              {pacing.has_target && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => deleteMutation.mutate()}
                  disabled={deleteMutation.isPending}
                  className="h-8 text-xs text-rose-600 hover:text-rose-700"
                >
                  <Trash2 size={13} className="mr-1" /> Remove
                </Button>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsEditing(false)}
                className="h-8 text-xs"
              >
                Cancel
              </Button>
            </div>
          </div>
          {errorMsg && <p className="mt-2 text-xs text-rose-600">{errorMsg}</p>}
        </form>
      )}

      {!pacing.has_target ? (
        <div className="mt-5 flex flex-col items-center justify-center rounded-xl border border-dashed py-8 text-center">
          <Target size={28} className="text-muted" />
          <h3 className="mt-2 text-sm font-semibold text-ink">No Revenue Target Set for {monthLabel}</h3>
          <p className="mt-1 max-w-md text-xs text-muted">
            You've generated {money(pacing.current_revenue)} in {monthLabel} so far. Set a monthly revenue goal to see
            real-time pacing, run-rate projections, and daily targets.
          </p>
          <Button
            size="sm"
            onClick={() => setIsEditing(true)}
            className="mt-4 h-8 text-xs font-medium"
          >
            Set {monthLabel} Target
          </Button>
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          {/* Headline Takeaway */}
          <div className="rounded-xl border border-blue-100 bg-blue-50/50 p-3.5 dark:border-blue-900/40 dark:bg-blue-950/20">
            <p className="text-xs font-semibold uppercase tracking-wider text-blue-700 dark:text-blue-300">
              Pacing Summary
            </p>
            <p className="mt-1 text-xs font-medium leading-relaxed text-ink">{pacing.headline}</p>
          </div>

          {/* Progress Bar with Expected Pace Marker */}
          <div>
            <div className="flex justify-between text-xs font-medium text-muted mb-1.5">
              <span>
                Progress: <strong className="text-ink">{money(pacing.current_revenue)}</strong> of{" "}
                {money(pacing.target_amount)}
              </span>
              <span className="font-bold text-ink">{pacing.progress_pct}%</span>
            </div>
            <div className="relative h-4 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div
                className={cn("h-full transition-all duration-500 rounded-full", currentStatus.barColor)}
                style={{ width: `${progressClamped}%` }}
              />
              {expectedPacePct > 0 && expectedPacePct < 100 && (
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-slate-400 dark:bg-slate-500"
                  style={{ left: `${expectedPacePct}%` }}
                  title={`Expected pace by day ${pacing.days_elapsed}: ${money(pacing.expected_pace_amount)}`}
                />
              )}
            </div>
            <div className="mt-1.5 flex justify-between text-[11px] text-muted">
              <span>
                Day {pacing.days_elapsed} of {pacing.days_in_month} ({pacing.days_remaining} days left)
              </span>
              <span>
                Expected pace: <strong className="text-ink">{money(pacing.expected_pace_amount)}</strong>
              </span>
            </div>
          </div>

          {/* 4-Stat Metric Row */}
          <div className="grid gap-3 grid-cols-2 sm:grid-cols-4 pt-1">
            <div className="rounded-xl border bg-surface p-3">
              <p className="text-[11px] font-semibold text-muted uppercase">Target Goal</p>
              <p className="mt-1 text-lg font-bold text-ink">{money(pacing.target_amount)}</p>
              <p className="mt-0.5 text-[11px] text-muted">For {monthLabel}</p>
            </div>
            <div className="rounded-xl border bg-surface p-3">
              <p className="text-[11px] font-semibold text-muted uppercase">Current Revenue</p>
              <p className="mt-1 text-lg font-bold text-ink">{money(pacing.current_revenue)}</p>
              <p className="mt-0.5 text-[11px] text-emerald-600 font-medium">{pacing.progress_pct}% reached</p>
            </div>
            <div className="rounded-xl border bg-surface p-3">
              <p className="text-[11px] font-semibold text-muted uppercase">Projected End</p>
              <p className="mt-1 text-lg font-bold text-ink">{money(pacing.projected_revenue)}</p>
              <p className="mt-0.5 text-[11px] text-muted">At current velocity</p>
            </div>
            <div className="rounded-xl border bg-surface p-3">
              <p className="text-[11px] font-semibold text-muted uppercase">Daily Needed</p>
              <p className="mt-1 text-lg font-bold text-ink">{money(pacing.daily_needed_remaining)}</p>
              <p className="mt-0.5 text-[11px] text-muted">For next {pacing.days_remaining} days</p>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}



