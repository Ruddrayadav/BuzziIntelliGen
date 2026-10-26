import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Calendar, FileText, LoaderCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  AttentionPanel,
  Compare,
  Diagnosis,
  EmptyDashboard,
  Overview,
  PageError,
  PageLoading,
  tabs,
  Unusual,
  type Granularity,
  type Tab,
} from "@/components/dashboard";

export function DashboardPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [granularity, setGranularity] = useState<Granularity>("daily");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  const dashboard = useQuery({
    queryKey: ["dashboard", startDate, endDate],
    queryFn: () => api.dashboard(startDate || undefined, endDate || undefined),
  });
  const comparison = useQuery({ queryKey: ["analytics", "compare"], queryFn: () => api.compare() });
  const anomalies = useQuery({ queryKey: ["analytics", "anomalies"], queryFn: api.anomalies });
  const diagnosis = useQuery({ queryKey: ["analytics", "diagnosis"], queryFn: () => api.diagnosis() });

  if (dashboard.isPending) return <PageLoading />;
  if (dashboard.isError) return <PageError error={dashboard.error} retry={() => void dashboard.refetch()} />;
  const data = dashboard.data;
  const isEmpty = data.revenue_trend.length === 0 && data.expense_breakdown.length === 0;

  const handleExportPdf = async () => {
    setIsExportingPdf(true);
    setPdfError(null);
    try {
      let targetMonth: string | undefined = undefined;
      if (startDate && startDate.length >= 7) {
        targetMonth = startDate.slice(0, 7);
      }
      await api.downloadMonthlyPdf(targetMonth);
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : "Failed to download PDF report");
    } finally {
      setIsExportingPdf(false);
    }
  };

  const handleAttentionNavigate = (targetTab: string) => {
    const mappedTab: Tab =
      targetTab === "diagnostics"
        ? "diagnosis"
        : targetTab === "comparison"
        ? "compare"
        : targetTab === "anomalies"
        ? "unusual"
        : "overview";
    setTab(mappedTab);
  };

  return (
    <section>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">Business dashboard</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">A clear view of your business.</h1>
          <p className="mt-2 text-muted">The numbers below come directly from the files you imported.</p>
        </div>

        {/* Action Controls: Date Range Filter & PDF Export Button */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-surface p-2 text-xs">
            <Calendar size={14} className="text-muted ml-1" />
            <div className="flex items-center gap-1.5">
              <label htmlFor="filter-start" className="text-muted">From</label>
              <input
                id="filter-start"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="rounded-lg border bg-background px-2 py-1 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </div>
            <div className="flex items-center gap-1.5">
              <label htmlFor="filter-end" className="text-muted">To</label>
              <input
                id="filter-end"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="rounded-lg border bg-background px-2 py-1 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </div>
            {(startDate || endDate) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setStartDate("");
                  setEndDate("");
                }}
                className="h-7 px-2 text-xs text-muted hover:text-ink"
              >
                <X size={13} className="mr-1" /> Reset
              </Button>
            )}
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleExportPdf}
            disabled={isExportingPdf || isEmpty}
            className="h-10 gap-1.5 rounded-xl border bg-surface px-3 text-xs font-semibold hover:bg-surface-hover"
            title="Download executive monthly PDF report"
          >
            {isExportingPdf ? (
              <>
                <LoaderCircle size={14} className="animate-spin text-brand" />
                <span>Generating PDF...</span>
              </>
            ) : (
              <>
                <FileText size={14} className="text-brand" />
                <span>Export Report (PDF)</span>
              </>
            )}
          </Button>
        </div>
      </div>

      {pdfError && (
        <div className="mt-3 flex items-center justify-between rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
          <span>{pdfError}</span>
          <button onClick={() => setPdfError(null)} className="text-rose-600 hover:text-rose-800">
            <X size={14} />
          </button>
        </div>
      )}

      {/* "What Needs Your Attention" Panel */}
      {data.attention_items && data.attention_items.length > 0 && !isEmpty && (
        <AttentionPanel
          items={data.attention_items}
          onNavigate={handleAttentionNavigate}
        />
      )}

      <div className="mt-6 flex gap-2 overflow-x-auto border-b" role="tablist" aria-label="Dashboard sections">
        {tabs.map((item) => (
          <button
            key={item.value}
            role="tab"
            aria-selected={tab === item.value}
            onClick={() => setTab(item.value)}
            className={cn(
              "shrink-0 border-b-2 px-3 py-3 text-sm font-semibold transition-colors",
              tab === item.value ? "border-brand text-brand" : "border-transparent text-muted hover:text-ink"
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {isEmpty ? (
        <EmptyDashboard />
      ) : (
        <div className="mt-7">
          {tab === "overview" && (
            <Overview
              data={data}
              comparison={comparison.data ?? null}
              granularity={granularity}
              setGranularity={setGranularity}
              startDate={startDate}
              endDate={endDate}
            />
          )}
          {tab === "compare" && <Compare comparison={comparison.data ?? null} loading={comparison.isPending} error={comparison.error} />}
          {tab === "unusual" && <Unusual report={anomalies.data ?? null} loading={anomalies.isPending} error={anomalies.error} />}
          {tab === "diagnosis" && <Diagnosis diagnosis={diagnosis.data ?? null} loading={diagnosis.isPending} error={diagnosis.error} />}
        </div>
      )}
    </section>
  );
}
