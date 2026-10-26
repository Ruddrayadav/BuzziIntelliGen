import React from "react";
import { Card } from "@/components/ui/card";
import { signedPercent } from "@/lib/format";

export function Details({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows || rows.length === 0) return null;
  const firstRow = rows[0];
  if (!firstRow || typeof firstRow !== "object") return null;
  const columns = Object.keys(firstRow);
  return (
    <details className="mt-4 rounded-xl border p-3">
      <summary className="cursor-pointer text-xs font-semibold text-muted hover:text-ink">
        Show data table ({rows.length} rows)
      </summary>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="text-muted border-b">
            <tr>
              {columns.map((column) => (
                <th key={column} className="px-2 py-2 font-medium">
                  {column.replace(/_/g, " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-t border-slate-100 dark:border-slate-800">
                {columns.map((column) => {
                  const val = row[column];
                  let displayVal = String(val ?? "—");
                  if (column.toLowerCase().includes("pct") || column.toLowerCase().includes("percent")) {
                    if (val === null || val === undefined) {
                      displayVal = "new";
                    } else if (typeof val === "number") {
                      displayVal = signedPercent(val);
                    }
                  }
                  return (
                    <td key={column} className="px-2 py-1.5">
                      {displayVal}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export function ChartCard({
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
