import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { AlertCircle, ArrowLeftRight, Check, ChevronDown, FileSpreadsheet, History, LoaderCircle, UploadCloud } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, ApiError, type FileType, type UploadPreview, type UploadResult } from "@/lib/api";
import { cn } from "@/lib/utils";

type UploadStatus = "checking" | "ready" | "importing" | "conflict" | "done" | "error";
type UploadEntry = {
  id: string;
  file: File;
  status: UploadStatus;
  selectedType?: FileType;
  preview?: UploadPreview;
  mapping: Record<string, string | null>;
  result?: UploadResult;
  error?: string;
  conflictMessage?: string;
};

const fields: Record<FileType, Array<{ value: string; label: string }>> = {
  sales: [
    { value: "date", label: "Sale date" }, { value: "order_id", label: "Order number" },
    { value: "product", label: "Product" }, { value: "category", label: "Product group" },
    { value: "quantity", label: "Quantity" }, { value: "unit_price", label: "Unit price" },
    { value: "revenue", label: "Sales amount" },
  ],
  expenses: [
    { value: "date", label: "Expense date" }, { value: "category", label: "Expense group" },
    { value: "description", label: "Description" }, { value: "amount", label: "Expense amount" },
  ],
  cashbook: [],
};

const requiredFields: Record<FileType, string[]> = {
  sales: ["date", "product", "revenue"],
  expenses: ["date", "category", "amount"],
  cashbook: [],
};

function getMissingRequired(mapping: Record<string, string | null>, fileType: FileType): string[] {
  if (fileType === "cashbook") return [];
  const mappedTargets = new Set(Object.values(mapping).filter((v): v is string => Boolean(v)));
  return requiredFields[fileType].filter((req) => !mappedTargets.has(req));
}

function getDuplicateTargets(mapping: Record<string, string | null>): string[] {
  const counts: Record<string, number> = {};
  for (const target of Object.values(mapping)) {
    if (target) counts[target] = (counts[target] || 0) + 1;
  }
  return Object.keys(counts).filter((k) => counts[k] > 1);
}

export function UploadPage() {
  const [uploads, setUploads] = useState<UploadEntry[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  function updateEntry(id: string, update: (entry: UploadEntry) => UploadEntry) {
    setUploads((current) => current.map((entry) => entry.id === id ? update(entry) : entry));
  }

  async function loadPreview(id: string, file: File, override?: FileType) {
    updateEntry(id, (entry) => ({ ...entry, status: "checking", error: undefined }));
    try {
      const preview = await api.previewUpload(file, override);
      updateEntry(id, (entry) => ({ ...entry, preview, selectedType: preview.file_type, mapping: preview.suggested_mapping, status: "ready" }));
    } catch (reason) {
      updateEntry(id, (entry) => ({ ...entry, status: "error", error: messageFor(reason) }));
    }
  }

  function addFiles(files: FileList | File[]) {
    Array.from(files).forEach((file) => {
      const id = `${file.name}-${file.lastModified}-${crypto.randomUUID()}`;
      setUploads((current) => [...current, { id, file, status: "checking", mapping: {} }]);
      void loadPreview(id, file);
    });
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    if (event.target.files) addFiles(event.target.files);
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
  }

  async function importSingleFile(entry: UploadEntry, replace = false) {
    if (!entry.selectedType) return;
    updateEntry(entry.id, (item) => ({ ...item, status: "importing", error: undefined, conflictMessage: undefined }));
    try {
      const mapping: Record<string, string> = {};
      Object.entries(entry.mapping).forEach(([raw, value]) => { if (value) mapping[raw] = value; });
      const result = await api.commitUpload(entry.file, entry.selectedType, mapping, replace);
      updateEntry(entry.id, (item) => ({ ...item, status: "done", result }));
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        updateEntry(entry.id, (item) => ({
          ...item,
          status: "conflict",
          conflictMessage: reason.message,
        }));
      } else {
        updateEntry(entry.id, (item) => ({ ...item, status: "error", error: messageFor(reason) }));
      }
    }
  }

  async function importFiles() {
    for (const entry of uploads.filter((item) => item.status === "ready" && item.selectedType)) {
      await importSingleFile(entry, false);
    }
  }

  function skipEntry(id: string) {
    setUploads((current) => current.filter((entry) => entry.id !== id));
  }

  function replaceEntry(entry: UploadEntry) {
    void importSingleFile(entry, true);
  }

  const active = uploads.some((entry) => entry.status === "checking" || entry.status === "importing");
  const readyEntries = uploads.filter((item) => item.status === "ready");
  const hasReady = readyEntries.length > 0;
  const canImport = hasReady && !active && readyEntries.every((entry) => {
    const fType = entry.selectedType || entry.preview?.file_type || "sales";
    if (fType === "cashbook") return true;
    return getMissingRequired(entry.mapping, fType).length === 0 && getDuplicateTargets(entry.mapping).length === 0;
  });
  const hasDone = uploads.some((entry) => entry.status === "done");
  const step = hasDone && !active && !hasReady ? 4 : active && uploads.some((entry) => entry.status === "importing") ? 3 : uploads.length ? 2 : 1;

  return <section>
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="eyebrow">Add your business files</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Bring your sales and expense records together.</h1>
        <p className="mt-3 max-w-2xl leading-7 text-muted">Start with the files you already export from your billing or accounting tool. We will show what we found before anything is saved.</p>
      </div>
      <Button asChild variant="outline" size="sm" className="gap-1.5 text-xs w-fit">
        <Link to="/history">
          <History size={14} /> View Import History
        </Link>
      </Button>
    </div>
    <Stepper step={step} />

    <button
      type="button"
      className={cn("mt-8 flex min-h-64 w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed bg-surface px-6 text-center transition-colors", dragging ? "border-brand bg-blue-50 dark:bg-blue-950" : "border-line hover:border-brand")}
      onClick={() => inputRef.current?.click()}
      onDragEnter={() => setDragging(true)}
      onDragLeave={() => setDragging(false)}
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
    >
      <span className="grid h-14 w-14 place-items-center rounded-2xl bg-blue-50 text-brand dark:bg-blue-950"><UploadCloud size={27} /></span>
      <span className="mt-5 text-lg font-semibold">Drop your business files here</span>
      <span className="mt-2 text-sm text-muted">Choose one or more CSV or Excel files. Maximum 10 MB each.</span>
      <span className="mt-5 rounded-xl border bg-surface px-4 py-2 text-sm font-semibold text-brand">Choose files</span>
      <input ref={inputRef} className="sr-only" type="file" accept=".csv,.xlsx,.xls" multiple onChange={onFileChange} />
    </button>

    {uploads.length > 0 && <div className="mt-8 space-y-5">
      {uploads.map((entry) => (
        <FileReview
          key={entry.id}
          entry={entry}
          onTypeChange={(fileType) => void loadPreview(entry.id, entry.file, fileType)}
          onMappingChange={(raw, mapped) => updateEntry(entry.id, (item) => ({ ...item, mapping: { ...item.mapping, [raw]: mapped || null } }))}
          onRetry={() => void loadPreview(entry.id, entry.file, entry.selectedType)}
          onSkip={skipEntry}
          onReplace={replaceEntry}
        />
      ))}
      {hasReady && (
        <div className="flex flex-col items-end gap-2">
          <Button onClick={() => void importFiles()} disabled={!canImport}>
            {active && <LoaderCircle className="animate-spin" size={17} />}
            Import files
          </Button>
          {!canImport && !active && (
            <p className="text-xs font-medium text-amber-600 dark:text-amber-400">
              Map all required fields and resolve duplicates before importing.
            </p>
          )}
        </div>
      )}
    </div>}


    {hasDone && <div className="mt-10 space-y-5"><div><p className="eyebrow">Import complete</p><h2 className="mt-2 text-2xl font-bold">Your files are ready to use.</h2></div>{uploads.filter((entry) => entry.status === "done" && entry.result).map((entry) => <ReconciliationCard key={entry.id} result={entry.result!} />)}<Button onClick={() => navigate("/dashboard")}>Go to dashboard</Button></div>}
  </section>;
}

function Stepper({ step }: { step: number }) {
  const labels = ["Upload", "Check", "Import", "Done"];
  return <ol className="mt-8 grid grid-cols-4 gap-2" aria-label="Import progress">{labels.map((label, index) => {
    const number = index + 1;
    const complete = number < step;
    const current = number === step;
    return <li key={label} className="flex min-w-0 items-center gap-2"><span className={cn("grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold", complete ? "bg-brand text-white" : current ? "bg-blue-100 text-brand dark:bg-blue-950" : "bg-slate-100 text-muted dark:bg-slate-800")}>{complete ? <Check size={15} /> : number}</span><span className={cn("hidden text-sm font-medium sm:inline", current ? "text-ink" : "text-muted")}>{label}</span></li>;
  })}</ol>;
}

function FileReview({
  entry,
  onTypeChange,
  onMappingChange,
  onRetry,
  onSkip,
  onReplace,
}: {
  entry: UploadEntry;
  onTypeChange: (type: FileType) => void;
  onMappingChange: (raw: string, mapped: string) => void;
  onRetry: () => void;
  onSkip: (id: string) => void;
  onReplace: (entry: UploadEntry) => void;
}) {
  if (entry.status === "checking") return <Card className="flex items-center gap-3 p-5"><LoaderCircle className="animate-spin text-brand" size={20} /><p>Checking <strong>{entry.file.name}</strong>…</p></Card>;
  if (entry.status === "importing") return <Card className="flex items-center gap-3 p-5"><LoaderCircle className="animate-spin text-brand" size={20} /><p>Importing <strong>{entry.file.name}</strong>…</p></Card>;
  if (entry.status === "conflict") {
    return (
      <Card className="border-amber-300 bg-amber-50/50 p-5 dark:border-amber-900 dark:bg-amber-950/20">
        <div className="flex gap-3">
          <AlertCircle className="shrink-0 text-amber-600 dark:text-amber-400" size={22} />
          <div className="space-y-2">
            <p className="font-semibold text-ink">File already imported</p>
            <p className="text-sm text-muted">{entry.conflictMessage ?? "This file has already been imported for your business."}</p>
            <div className="flex flex-wrap gap-2 pt-2">
              <Button size="sm" variant="default" onClick={() => onReplace(entry)}>
                Replace previous import
              </Button>
              <Button size="sm" variant="outline" onClick={() => onSkip(entry.id)}>
                Skip this file
              </Button>
            </div>
          </div>
        </div>
      </Card>
    );
  }
  if (entry.status === "error") return <Card className="border-red-200 p-5 dark:border-red-900"><div className="flex gap-3"><AlertCircle className="shrink-0 text-red-600" size={20} /><div><p className="font-semibold">We could not check {entry.file.name}</p><p className="mt-1 text-sm text-muted">{entry.error}</p><Button className="mt-4" size="sm" variant="outline" onClick={onRetry}>Try again</Button></div></div></Card>;
  if (entry.status === "done") return null;
  const preview = entry.preview!;
  const fileType = entry.selectedType || preview.file_type;
  const missing = getMissingRequired(entry.mapping, fileType);
  const duplicates = getDuplicateTargets(entry.mapping);
  const hasErrors = missing.length > 0 || duplicates.length > 0;
  const needsAttention = hasErrors || preview.columns.some((col) => entry.mapping[col] === null);

  return <Card className="p-5 sm:p-6"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div className="flex gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-50 text-brand dark:bg-blue-950"><FileSpreadsheet size={20} /></span><div><p className="font-semibold">{entry.file.name}</p><p className="mt-1 text-sm text-muted">{preview.raw_row_count} rows · {preview.columns.length} columns</p></div></div><div className="flex items-center gap-2"><TypeChip type={fileType} /><label className="sr-only" htmlFor={`type-${entry.id}`}>Change file type for {entry.file.name}</label><select id={`type-${entry.id}`} value={fileType} onChange={(event) => onTypeChange(event.target.value as FileType)} className="h-9 rounded-lg border bg-surface px-2 text-sm font-medium"><option value="sales">Sales</option><option value="expenses">Expenses</option><option value="cashbook">Cash-book (Split)</option></select></div></div>
    {fileType === "cashbook" ? (
      <div className="mt-6 rounded-xl border border-purple-200 bg-purple-50/60 p-4 dark:border-purple-900/50 dark:bg-purple-950/20">
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300">
            <ArrowLeftRight size={18} />
          </span>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-ink">Automatic Cash-book Separation</p>
            <p className="text-sm text-muted">
              {preview.cashbook_summary?.message || "This file contains both sales and expense transactions. BizIntel will automatically separate it into two clean imports."}
            </p>
            <div className="flex flex-wrap gap-2 pt-2">
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-100/80 px-2.5 py-1 text-xs font-semibold text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
                Sales: {preview.cashbook_summary?.sales_count ?? 0} rows (₹{(preview.cashbook_summary?.sales_total ?? 0).toLocaleString("en-IN")})
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-violet-100/80 px-2.5 py-1 text-xs font-semibold text-violet-800 dark:bg-violet-950/60 dark:text-violet-300">
                Expenses: {preview.cashbook_summary?.expenses_count ?? 0} rows (₹{(preview.cashbook_summary?.expenses_total ?? 0).toLocaleString("en-IN")})
              </span>
            </div>
          </div>
        </div>
      </div>
    ) : (
      <>
        <div className="mt-6 rounded-xl bg-slate-50 p-4 dark:bg-slate-900">
          <p className="text-sm font-semibold">What we understood</p>
          <div className="mt-3 space-y-2 text-sm text-muted">
            {Object.entries(entry.mapping).filter(([, target]) => target).map(([raw, target]) => (
              <p key={raw}>We read <strong className="font-medium text-ink">“{raw}”</strong> as <strong className="font-medium text-ink">{friendlyField(target!, fileType)}</strong>.</p>
            ))}
          </div>
        </div>
        <details className="mt-4 rounded-xl border p-4" open={needsAttention ? true : undefined}>
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-semibold">
            <span>Fix column mapping {hasErrors && <span className="ml-2 text-xs font-normal text-rose-600 dark:text-rose-400">(Action required)</span>}</span>
            <ChevronDown size={18} />
          </summary>
          {missing.length > 0 && (
            <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-100">
              Please choose columns for required field(s): {missing.map((field) => friendlyField(field, fileType)).join(", ")}.
            </p>
          )}
          {duplicates.length > 0 && (
            <p className="mt-3 rounded-lg bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950 dark:text-rose-100">
              Multiple columns are mapped to the same field: {duplicates.map((field) => friendlyField(field, fileType)).join(", ")}. Each field can only be mapped to one column.
            </p>
          )}
          <div className="mt-4 space-y-3">
            {preview.columns.map((raw) => (
              <label key={raw} className="grid gap-2 text-sm font-medium sm:grid-cols-2 sm:items-center">
                <span>{raw}</span>
                <select
                  value={entry.mapping[raw] ?? ""}
                  onChange={(event) => onMappingChange(raw, event.target.value)}
                  className={cn("h-10 rounded-lg border bg-surface px-2 font-normal", duplicates.includes(entry.mapping[raw] ?? "") ? "border-rose-500 focus:ring-rose-500" : "")}
                >
                  <option value="">Do not use this column</option>
                  {fields[fileType].map((field) => <option key={field.value} value={field.value}>{field.label}</option>)}
                </select>
              </label>
            ))}
          </div>
        </details>
      </>
    )}
    <PreviewTable columns={preview.columns} rows={preview.sample_rows} />
  </Card>;
}

function TypeChip({ type }: { type: FileType }) {
  if (type === "cashbook") {
    return <span className="rounded-full bg-purple-100 px-3 py-1 text-sm font-semibold text-purple-800 dark:bg-purple-950 dark:text-purple-200">Cash-book</span>;
  }
  return <span className={cn("rounded-full px-3 py-1 text-sm font-semibold", type === "sales" ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200" : "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-200")}>{type === "sales" ? "Sales" : "Expenses"}</span>;
}

function PreviewTable({ columns, rows }: { columns: string[]; rows: Record<string, unknown>[] }) {
  return <div className="mt-5 overflow-x-auto"><p className="mb-2 text-sm font-semibold">First 5 rows</p><table className="min-w-full overflow-hidden rounded-xl border text-left text-sm"><thead className="bg-slate-50 text-muted dark:bg-slate-900"><tr>{columns.map((column) => <th key={column} className="whitespace-nowrap px-3 py-2 font-medium">{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index} className="border-t">{columns.map((column) => <td key={column} className="max-w-48 truncate px-3 py-2">{displayValue(row[column])}</td>)}</tr>)}</tbody></table></div>;
}

function ReconciliationCard({ result }: { result: UploadResult }) {
  const hasWarnings = Boolean(result.rows_with_warnings && result.rows_with_warnings > 0);
  return (
    <Card className="p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">
          <Check size={20} />
        </span>
        <div>
          <p className="font-semibold">{result.filename}</p>
          <p className="mt-1 text-sm text-muted">
            {result.is_cashbook && result.cashbook_summary
              ? result.cashbook_summary
              : "Your import was saved and is ready for the dashboard."}
          </p>
        </div>
      </div>
      <div className={cn("mt-5 grid gap-3", hasWarnings ? "sm:grid-cols-4" : "sm:grid-cols-3")}>
        <Count label="Rows in file" value={result.rows_read} />
        <Count label="Saved" value={result.rows_saved} />
        {hasWarnings && (
          <Count label="Saved with warnings" value={result.rows_with_warnings!} />
        )}
        <Count label="Skipped" value={result.rows_skipped} />
      </div>
      {result.warnings.length > 0 && <p className="mt-4 text-sm text-muted">{result.warnings.join(" ")}</p>}
      {result.skipped_rows.length > 0 && (
        <details className="mt-5 rounded-xl border p-4">
          <summary className="cursor-pointer font-semibold">See skipped rows and reasons</summary>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b text-muted">
                  <th className="px-2 py-2">Row</th>
                  <th className="px-2 py-2">Reason</th>
                  <th className="px-2 py-2">Data</th>
                </tr>
              </thead>
              <tbody>
                {result.skipped_rows.map((row) => (
                  <tr key={row.original_index} className="border-b">
                    <td className="px-2 py-2">{row.original_index + 1}</td>
                    <td className="px-2 py-2">{row.reason}</td>
                    <td className="px-2 py-2">
                      {Object.entries(row.original_row)
                        .map(([key, value]) => `${key}: ${displayValue(value)}`)
                        .join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button className="mt-4" size="sm" variant="outline" onClick={() => downloadSkippedRows(result)}>
            Download skipped rows (CSV)
          </Button>
        </details>
      )}
    </Card>
  );
}

function Count({ label, value }: { label: string; value: number }) { return <div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-900"><p className="text-sm text-muted">{label}</p><p className="mt-1 text-xl font-bold">{value}</p></div>; }
function friendlyField(field: string, type: FileType) { return fields[type].find((item) => item.value === field)?.label ?? field; }
function displayValue(value: unknown) { return value === null || value === undefined ? "—" : String(value); }
function messageFor(reason: unknown) { return reason instanceof ApiError ? reason.message : "We could not reach the server. Please try again."; }

function downloadSkippedRows(result: UploadResult) {
  // Neutralise Excel/CSV formula injection: prefix with single quote if it starts with =, +, -, @
  const escape = (value: unknown) => {
    let s = String(value ?? "");
    if (/^[=+\-@]/.test(s)) s = `'${s}`;
    return `"${s.replace(/"/g, '""')}"`;
  };
  const columns = ["row_number", "reason", ...Object.keys(result.skipped_rows[0]?.original_row ?? {})];
  const csv = [columns.join(","), ...result.skipped_rows.map((row) => [row.original_index + 1, row.reason, ...columns.slice(2).map((column) => row.original_row[column])].map(escape).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `skipped-rows-${result.filename}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

