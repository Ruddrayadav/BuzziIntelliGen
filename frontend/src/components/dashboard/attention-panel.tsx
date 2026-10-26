import { AlertCircle, AlertTriangle, ArrowRight, CheckCircle2 } from "lucide-react";
import type { AttentionItem } from "@/lib/api";
import { cn } from "@/lib/utils";

export function AttentionPanel({
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
                    onClick={() => onNavigate(item.action_tab!)}
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
