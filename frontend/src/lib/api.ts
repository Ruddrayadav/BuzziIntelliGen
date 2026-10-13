export type PublicUser = { username: string; business_name: string };
export type Credentials = { username: string; password: string };
export type RegisterInput = Credentials & { business_name: string };
export type FileType = "sales" | "expenses";

export type UploadPreview = {
  filename: string;
  detected_type: FileType;
  file_type: FileType;
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
  rows_read: number;
  rows_saved: number;
  rows_skipped: number;
  duplicates_removed: number;
  skipped_rows: Array<{ original_index: number; original_row: Record<string, unknown>; reason: string }>;
  warnings: string[];
};

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isFormData = init.body instanceof FormData;
  const response = await fetch(`${import.meta.env.VITE_API_URL ?? ""}${path}`, {
    credentials: "include",
    ...init,
    headers: { ...(isFormData ? {} : { "Content-Type": "application/json" }), ...init.headers },
  });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => ({ message: "The server returned an unexpected response." }));
  if (!response.ok) throw new ApiError(body.message ?? "We could not complete that request.", response.status);
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
  commitUpload: (file: File, fileType: FileType, mapping: Record<string, string>) => {
    const form = new FormData();
    form.append("file", file);
    form.append("file_type", fileType);
    form.append("mapping", JSON.stringify(mapping));
    return request<UploadResult>("/api/upload/commit", { method: "POST", body: form });
  },
};
