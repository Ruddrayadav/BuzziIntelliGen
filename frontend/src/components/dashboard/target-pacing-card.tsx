import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Target, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, ApiError, type TargetPacing } from "@/lib/api";
import { money } from "@/lib/format";
import { cn } from "@/lib/utils";

export function TargetPacingCard({ pacing }: { pacing?: TargetPacing | null }) {
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
