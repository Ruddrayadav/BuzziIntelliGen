import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "@/components/ui/card";
import type { PeriodComparison } from "@/lib/api";
import { money } from "@/lib/format";
import { ChartCard, Details } from "./chart-card";
import { NoData, PageError, PanelLoading } from "./dashboard-states";
import { Delta } from "./kpi-cards";

export function Compare({
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
    {
      label: "Revenue",
      current: comparison.current.revenue,
      prior: comparison.prior.revenue,
      delta: comparison.revenue_delta,
      percent: comparison.revenue_delta_pct,
      invert: false,
    },
    {
      label: "Expenses",
      current: comparison.current.expenses,
      prior: comparison.prior.expenses,
      delta: comparison.expense_delta,
      percent: comparison.expense_delta_pct,
      invert: true,
    },
    {
      label: "Profit",
      current: comparison.current.net_profit,
      prior: comparison.prior.net_profit,
      delta: comparison.profit_delta,
      percent: comparison.profit_delta_pct,
      invert: false,
    },
    {
      label: "Average order value",
      current: comparison.current.average_order_value,
      prior: comparison.prior.average_order_value,
      delta: comparison.aov_delta,
      percent: comparison.aov_delta_pct,
      invert: false,
    },
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
  const gainerTakeaway =
    topGainer && topDecliner
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

      {comparison.expense_shifts && comparison.expense_shifts.length > 0 && (
        <Card className="p-6">
          <h3 className="font-semibold text-base">All expense shifts</h3>
          <p className="text-xs text-muted mt-1">Detailed period-over-period variance for all expense categories.</p>
          <Details rows={comparison.expense_shifts} />
        </Card>
      )}
    </div>
  );
}
