import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Eye,
  FileSpreadsheet,
  History,
  LoaderCircle,
  RotateCcw,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, ApiError, type SkippedRowItem, type UploadHistoryItem } from "@/lib/api";
import { plainDate } from "@/lib/format";
import { cn } from "@/lib/utils";

export function HistoryPage() {
  const queryClient = useQueryClient();
  const [selectedSkippedUpload, setSelectedSkippedUpload] = useState<UploadHistoryItem | null>(null);
  const [uploadToUndo, setUploadToUndo] = useState<UploadHistoryItem | null>(null);
  const [undoError, setUndoError] = useState("");
  const [successBanner, setSuccessBanner] = useState("");

  const historyQuery = useQuery({
    queryKey: ["uploadHistory"],
    queryFn: api.uploadHistory,
  });

  const skippedQuery = useQuery({
    queryKey: ["uploadSkippedRows", selectedSkippedUpload?.id],
    queryFn: () => (selectedSkippedUpload ? api.uploadSkippedRows(selectedSkippedUpload.id) : Promise.resolve([])),
    enabled: !!selectedSkippedUpload,
  });

  const undoMutation = useMutation({
    mutationFn: (uploadId: number) => api.undoUpload(uploadId),
    onSuccess: (data) => {
      setSuccessBanner(data.message || "Import successfully undone.");
      setUploadToUndo(null);
      setUndoError("");
      queryClient.invalidateQueries({ queryKey: ["uploadHistory"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) => {
      setUndoError(err instanceof ApiError ? err.message : "Failed to undo import.");
    },
  });

  if (historyQuery.isPending) {
    return (
      <div className="grid min-h-64 place-items-center text-muted">
        <span className="inline-flex items-center gap-2">
          <LoaderCircle className="animate-spin" size={19} /> Loading import history…
        </span>
      </div>
    );
  }

  if (historyQuery.isError) {
    return (
      <Card className="mx-auto mt-7 max-w-xl p-6 text-center">
        <AlertCircle className="mx-auto text-rose-600" />
        <h2 className="mt-3 font-bold">Could not load import history</h2>
        <p className="mt-2 text-sm text-muted">
          {historyQuery.error instanceof ApiError ? historyQuery.error.message : "Network error"}
        </p>
        <Button className="mt-5" variant="outline" onClick={() => void historyQuery.refetch()}>
          Try again
        </Button>
      </Card>
    );
  }

  const items = historyQuery.data ?? [];

  return (
    <section className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">Audit & Rollback</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Import History</h1>
          <p className="mt-2 text-muted">
            Track past file uploads, inspect skipped row reasons, or undo any import to keep your metrics accurate.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline" size="sm" className="gap-1.5 text-xs">
            <Link to="/upload">
              <Upload size={14} /> Upload new files
            </Link>
          </Button>
        </div>
      </div>

      {/* Success Notification Banner */}
      {successBanner && (
        <div className="flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50/80 p-4 text-xs font-medium text-emerald-900 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-200">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} className="text-emerald-600 dark:text-emerald-400" />
            <span>{successBanner}</span>
          </div>
          <button
            type="button"
            onClick={() => setSuccessBanner("")}
            className="text-emerald-700 hover:text-emerald-950 dark:text-emerald-300"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* History List or Empty State */}
      {items.length === 0 ? (
        <Card className="mx-auto mt-8 max-w-xl p-8 text-center">
          <History className="mx-auto text-muted" size={32} />
          <h2 className="mt-4 text-lg font-bold">No import history yet</h2>
          <p className="mt-2 text-sm text-muted">
            When you import sales or expense spreadsheets, they will be logged here with row audit records and rollback
            capabilities.
          </p>
          <Button className="mt-6 gap-2" asChild>
            <Link to="/upload">
              <Upload size={15} /> Upload your first file
            </Link>
          </Button>
        </Card>
      ) : (
        <Card className="overflow-hidden p-0">
          <div className="border-b bg-surface px-6 py-4">
            <h2 className="text-sm font-bold text-ink">Recorded Imports ({items.length})</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="border-b bg-slate-50/50 text-muted dark:bg-slate-900/40">
                <tr>
                  <th className="px-5 py-3.5 font-semibold">File & Upload Date</th>
                  <th className="px-5 py-3.5 font-semibold">Type</th>
                  <th className="px-5 py-3.5 font-semibold">Rows Saved</th>
                  <th className="px-5 py-3.5 font-semibold">Rows Skipped</th>
                  <th className="px-5 py-3.5 font-semibold">Status</th>
                  <th className="px-5 py-3.5 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {items.map((item) => {
                  const typeStyles: Record<string, string> = {
                    sales: "bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-200",
                    expenses: "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-200",
                    cashbook: "bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-200",
                  };

                  return (
                    <tr key={item.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-900/30">
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-2.5">
                          <span className="grid h-8 w-8 place-items-center rounded-lg bg-slate-100 text-muted dark:bg-slate-800">
                            <FileSpreadsheet size={16} />
                          </span>
                          <div>
                            <p className="font-bold text-ink">{item.filename}</p>
                            <p className="text-[11px] text-muted">
                              {item.uploaded_at ? plainDate(item.uploaded_at) : "Recent"}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <span
                          className={cn(
                            "inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider",
                            typeStyles[item.file_type] || "bg-slate-100 text-slate-800"
                          )}
                        >
                          {item.file_type}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                          {item.rows_saved.toLocaleString()} rows
                        </span>
                        <span className="block text-[10px] text-muted">of {item.rows_raw.toLocaleString()} read</span>
                      </td>
                      <td className="px-5 py-4">
                        {item.rows_skipped > 0 ? (
                          <button
                            type="button"
                            onClick={() => setSelectedSkippedUpload(item)}
                            className="inline-flex items-center gap-1 font-semibold text-amber-600 hover:underline dark:text-amber-400"
                          >
                            <span>{item.rows_skipped} skipped</span>
                            <Eye size={12} />
                          </button>
                        ) : (
                          <span className="text-muted">0 skipped</span>
                        )}
                      </td>
                      <td className="px-5 py-4">
                        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-muted dark:bg-slate-800">
                          <CheckCircle2 size={12} className="text-emerald-500" />
                          {item.status}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {item.rows_skipped > 0 && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setSelectedSkippedUpload(item)}
                              className="h-8 text-xs text-muted hover:text-ink"
                            >
                              Audit Skipped
                            </Button>
                          )}
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setUploadToUndo(item);
                              setUndoError("");
                            }}
                            className="h-8 gap-1.5 text-xs text-rose-600 hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-950/20"
                          >
                            <RotateCcw size={13} />
                            Undo Import
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Skipped Rows Modal */}
      {selectedSkippedUpload && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-3xl rounded-2xl border bg-surface p-6 shadow-xl">
            <div className="flex items-center justify-between border-b pb-3.5">
              <div className="flex items-center gap-2.5">
                <span className="grid h-8 w-8 place-items-center rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400">
                  <AlertTriangle size={18} />
                </span>
                <div>
                  <h2 className="text-base font-bold text-ink">
                    Skipped Rows Audit: {selectedSkippedUpload.filename}
                  </h2>
                  <p className="text-xs text-muted">
                    {selectedSkippedUpload.rows_skipped} rows were rejected during cleaning to protect report integrity.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedSkippedUpload(null)}
                className="rounded-lg p-1 text-muted hover:bg-slate-100 hover:text-ink dark:hover:bg-slate-800"
              >
                <X size={18} />
              </button>
            </div>

            <div className="mt-4 max-h-[60vh] overflow-y-auto">
              {skippedQuery.isPending ? (
                <div className="py-12 text-center text-muted">
                  <LoaderCircle className="mx-auto animate-spin" size={20} />
                  <p className="mt-2 text-xs">Loading skipped rows…</p>
                </div>
              ) : skippedQuery.data && skippedQuery.data.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-left text-xs">
                    <thead className="border-b bg-slate-50/50 text-muted dark:bg-slate-900/40">
                      <tr>
                        <th className="px-3 py-2.5 font-semibold">Reason</th>
                        <th className="px-3 py-2.5 font-semibold">Raw Row Data</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                      {skippedQuery.data.map((row) => (
                        <tr key={row.id}>
                          <td className="px-3 py-2.5 font-semibold text-rose-600 dark:text-rose-400 whitespace-nowrap">
                            {row.reason}
                          </td>
                          <td className="px-3 py-2.5 font-mono text-[11px] text-muted max-w-md break-all">
                            {JSON.stringify(row.row_data)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="py-8 text-center text-xs text-muted">No detailed row records found.</p>
              )}
            </div>

            <div className="mt-5 flex justify-end border-t pt-3.5">
              <Button size="sm" onClick={() => setSelectedSkippedUpload(null)}>
                Close Audit
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Undo Confirmation Modal */}
      {uploadToUndo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border bg-surface p-6 shadow-xl">
            <div className="flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-rose-500/10 text-rose-600 dark:text-rose-400">
                <Trash2 size={20} />
              </span>
              <div>
                <h2 className="text-base font-bold text-ink">Undo and Delete Import?</h2>
                <p className="text-xs text-muted">This action is permanent and cannot be reversed.</p>
              </div>
            </div>

            <div className="mt-4 rounded-xl border border-rose-100 bg-rose-50/50 p-4 text-xs text-rose-950 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200">
              <p className="font-semibold">You are rolling back: '{uploadToUndo.filename}'</p>
              <p className="mt-1 leading-relaxed text-muted dark:text-rose-300">
                This will permanently delete the upload record and all{" "}
                <strong className="text-ink dark:text-white font-bold">{uploadToUndo.rows_saved} saved rows</strong> from
                your charts, metrics, and comparisons.
              </p>
            </div>

            {undoError && <p className="mt-3 text-xs text-rose-600">{undoError}</p>}

            <div className="mt-5 flex justify-end gap-2 border-t pt-3.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setUploadToUndo(null);
                  setUndoError("");
                }}
                disabled={undoMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => undoMutation.mutate(uploadToUndo.id)}
                disabled={undoMutation.isPending}
                className="gap-1.5 bg-rose-600 text-white hover:bg-rose-700"
              >
                {undoMutation.isPending ? (
                  <>
                    <LoaderCircle className="animate-spin" size={14} />
                    Undoing…
                  </>
                ) : (
                  <>
                    <RotateCcw size={14} />
                    Yes, Undo Import
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
