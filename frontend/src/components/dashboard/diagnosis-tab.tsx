import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "@/components/ui/card";
import type { ProfitDiagnosis } from "@/lib/api";
import { money } from "@/lib/format";
import { ChartCard, Details } from "./chart-card";
import { NoData, PageError, PanelLoading } from "./dashboard-states";

export function Diagnosis({
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
