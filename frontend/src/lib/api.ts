export type PublicUser = { username: string; business_name: string };
export type Credentials = { username: string; password: string };
export type RegisterInput = Credentials & { business_name: string };

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${import.meta.env.VITE_API_URL ?? ""}${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
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
};
