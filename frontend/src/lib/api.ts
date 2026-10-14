export type PublicUser = { username: string; business_name: string };
export type Credentials = { username: string; password: string };
export type RegisterInput = Credentials & { business_name: string };
export type FileType = "sales" | "expenses" | "cashbook";

export type CashbookSummary = {
  sales_count: number;
  expenses_count: number;
  sales_total: number;
  expenses_total: number;
  split_column: string;
  split_method: string;
  message: string;
};

export type UploadPreview = {
  filename: string;
  file_hash?: string;
  detected_type: FileType;
  file_type: FileType;
  is_cashbook?: boolean;
  cashbook_summary?: CashbookSummary;
  columns: string[];
  suggested_mapping: Record<string, string | null>;
  mapping_methods: Record<string, "rule" | "llm" | "unmapped">;
  missing_required: string[];
  sample_rows: Record<string, unknown>[];
  raw_row_count: number;
};

export type UploadResult = {
  success: boolean;
  upload_log_id: number;
  filename: string;
  file_type: FileType;
  is_cashbook?: boolean;
  cashbook_summary?: string;
  rows_read: number;
  rows_saved: number;
  rows_skipped: number;
  duplicates_removed: number;
  skipped_rows: Array<{ original_index: number; original_row: Record<string, unknown>; reason: string }>;
  warnings: string[];
};

export type DashboardData = {
  total_revenue: number;
  total_expenses: number;
  net_profit: number;
  average_order_value: number;
  revenue_trend: Array<{ date: string; revenue: number }>;
  top_products: Array<{ product: string; revenue: number }>;
  expense_breakdown: Array<{ category: string; amount: number }>;
};

export type PeriodSummary = {
  period_label: string;
  revenue: number;
  expenses: number;
  net_profit: number;
  order_count: number;
  average_order_value: number;
  profit_margin_pct: number;
};

export type PeriodComparison = {
  current: PeriodSummary;
  prior: PeriodSummary;
  revenue_delta: number;
  revenue_delta_pct: number;
  expense_delta: number;
  expense_delta_pct: number;
  profit_delta: number;
  profit_delta_pct: number;
  aov_delta: number;
  aov_delta_pct: number;
  margin_delta_pct: number;
  product_shifts: Array<Record<string, unknown>>;
  expense_shifts: Array<Record<string, unknown>>;
  top_gainers: Array<Record<string, unknown>>;
  top_decliners: Array<Record<string, unknown>>;
};

export type Anomaly = {
  date: string;
  metric: string;
  actual_value: number;
  expected_value: number;
  deviation: number;
  deviation_pct: number;
  z_score: number;
  anomaly_type: string;
  severity: "critical" | "warning" | "info";
  description: string;
};

export type AnomalyReport = {
  total_anomalies: number;
  revenue_anomalies: Anomaly[];
  expense_anomalies: Anomaly[];
  timeline_df: Array<Record<string, unknown>>;
};

export type ProfitDiagnosis = {
  period_label: string;
  comparison_label: string;
  prior_profit: number;
  current_profit: number;
  profit_change: number;
  profit_change_pct: number;
  is_profit_down: boolean;
  primary_driver: string;
  revenue_impact: number;
  expense_impact: number;
  top_revenue_drags: Array<Record<string, unknown>>;
  top_expense_surges: Array<Record<string, unknown>>;
  key_insights: string[];
  recommendations: string[];
  waterfall_df: Array<{ measure: string; label: string; value: number }>;
};

export type AskAnswer = {
  text: string;
  intent: string;
  table: { columns: string[]; rows: Array<Record<string, unknown>> };
};

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isFormData = init.body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(`${import.meta.env.VITE_API_URL ?? ""}${path}`, {
      credentials: "include",
      ...init,
      headers: { ...(isFormData ? {} : { "Content-Type": "application/json" }), ...init.headers },
    });
  } catch {
    throw new ApiError("We cannot reach the BizIntel server. Start the API, then try again.", 0);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (body === null) {
    const message = response.status >= 502
      ? "The BizIntel server is not running. Start it, then try again."
      : "The server returned an invalid response. Please try again.";
    throw new ApiError(message, response.status);
  }
  if (!response.ok) {
    const detailMsg = typeof body?.detail === "string" ? body.detail : body?.detail?.message;
    const msg = detailMsg ?? body?.message ?? "We could not complete that request.";
    throw new ApiError(msg, response.status);
  }
  return body as T;
}

export const api = {
  me: () => request<PublicUser>("/api/auth/me"),
  login: (input: Credentials) => request<PublicUser>("/api/auth/login", { method: "POST", body: JSON.stringify(input) }),
  register: (input: RegisterInput) => request<PublicUser>("/api/auth/register", { method: "POST", body: JSON.stringify(input) }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  previewUpload: (file: File, fileType?: FileType) => {
    const form = new FormData();
    form.append("file", file);
    if (fileType) form.append("file_type", fileType);
    return request<UploadPreview>("/api/upload/preview", { method: "POST", body: form });
  },
  commitUpload: (file: File, fileType: FileType, mapping: Record<string, string>, replace = false) => {
    const form = new FormData();
    form.append("file", file);
    form.append("file_type", fileType);
    form.append("mapping", JSON.stringify(mapping));
    if (replace) form.append("replace", "true");
    return request<UploadResult>("/api/upload/commit", { method: "POST", body: form });
  },
  dashboard: () => request<DashboardData>("/api/dashboard"),
  trend: (granularity: "daily" | "weekly" | "monthly" = "daily") =>
    request<Array<{ label: string; revenue: number; date?: string }>>(`/api/dashboard/trend?granularity=${granularity}`),
  months: () => request<{ months: string[] }>("/api/analytics/months"),
  compare: (currentMonth?: string, priorMonth?: string) => request<PeriodComparison | null>(`/api/analytics/compare${monthsQuery(currentMonth, priorMonth)}`),
  anomalies: () => request<AnomalyReport>("/api/analytics/anomalies"),
  diagnosis: (currentMonth?: string, priorMonth?: string) => request<ProfitDiagnosis | null>(`/api/analytics/diagnosis${monthsQuery(currentMonth, priorMonth)}`),
  ask: (question: string) => request<AskAnswer>("/api/ask", { method: "POST", body: JSON.stringify({ question }) }),
};

function monthsQuery(currentMonth?: string, priorMonth?: string) {
  const params = new URLSearchParams();
  if (currentMonth) params.set("current_month", currentMonth);
  if (priorMonth) params.set("prior_month", priorMonth);
  const query = params.toString();
  return query ? `?${query}` : "";
}
