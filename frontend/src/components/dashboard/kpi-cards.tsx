import React from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { signedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

export function Delta({ value, invert = false }: { value: number | null | undefined; invert?: boolean }) {
  if (value === null || value === undefined) {
    return (
      <span className="inline-flex items-center gap-1 font-semibold text-blue-600 bg-blue-50 dark:bg-blue-950/40 px-1.5 py-0.5 rounded text-xs">
        new
      </span>
    );
  }
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

export function KpiCard({
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
  delta?: number | null;
  priorPeriodLabel?: string;
  invertDelta?: boolean;
}) {
  const hasNoPrior =
    !priorPeriodLabel ||
    priorPeriodLabel === "None" ||
    priorPeriodLabel === "null" ||
    priorPeriodLabel === "—";

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
        {hasNoPrior || delta === undefined || delta === null ? (
          <p className="mt-2 text-xs text-muted">no earlier data</p>
        ) : (
          <p className="mt-2 text-xs">
            <Delta value={delta} invert={invertDelta} />
            <span className="ml-1 text-muted">vs {priorPeriodLabel}</span>
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

export function SimpleKpiCard({
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
