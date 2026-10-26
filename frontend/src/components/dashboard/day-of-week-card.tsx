import { Clock } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "@/components/ui/card";
import type { DayOfWeekDay, DayOfWeekInsight } from "@/lib/api";
import { money } from "@/lib/format";
import { Details } from "./chart-card";

export function DayOfWeekCard({ insight }: { insight?: DayOfWeekInsight | null }) {
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
