import { CheckCircle2, ShoppingBag } from "lucide-react";
import { Card } from "@/components/ui/card";
import type { SlowMoverItem } from "@/lib/api";
import { money } from "@/lib/format";
import { cn } from "@/lib/utils";

export function SlowMoversCard({ items }: { items?: SlowMoverItem[] }) {
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
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold",
                          statusStyles[item.status] ?? statusStyles.Moderate
                        )}
                      >
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
