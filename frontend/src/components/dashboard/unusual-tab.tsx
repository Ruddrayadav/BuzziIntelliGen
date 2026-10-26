import { Card } from "@/components/ui/card";
import type { Anomaly } from "@/lib/api";
import { money, plainDate, signedPercent } from "@/lib/format";
import { Details } from "./chart-card";
import { NoData, PageError, PanelLoading, Severity } from "./dashboard-states";

export function Unusual({
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
      <p className="mt-2 text-sm text-muted">
        These are days that differ noticeably from your usual operating baseline.
      </p>

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
