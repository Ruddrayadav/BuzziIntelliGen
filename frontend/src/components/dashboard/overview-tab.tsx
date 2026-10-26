import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LoaderCircle, Package, ReceiptText } from "lucide-react";
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
import { api, type DashboardData, type PeriodComparison } from "@/lib/api";
import { money } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ChartCard } from "./chart-card";
import { DayOfWeekCard } from "./day-of-week-card";
import { KpiCard, SimpleKpiCard } from "./kpi-cards";
import { SlowMoversCard } from "./slow-movers-card";
import { TargetPacingCard } from "./target-pacing-card";
import { palette, type Granularity, type ProductViewMode } from "./types";

export function Overview({
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
