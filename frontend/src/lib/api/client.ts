/**
 * Centralised API client.
 * - Sends credentials (session cookie) on every request.
 * - Reads the csrf_token cookie and echoes it in X-CSRF-Token on state-changing methods (D-04).
 * - Parses the standard { success, data } / { success, error } envelope.
 */

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const API_BASE = `${BACKEND_URL}/api/v1`;

export type ApiSuccess<T> = { success: true; data: T };
export type ApiError = {
  success: false;
  error: { code: string; message: string; details?: unknown };
};
export type ApiResult<T> = ApiSuccess<T> | ApiError;

export class ApiRequestError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

const STATE_CHANGING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<ApiSuccess<T>> {
  const method = (init.method ?? "GET").toUpperCase();

  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");

  if (STATE_CHANGING.has(method)) {
    const csrf = getCsrfToken();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include", // always send session cookie
  });

  if (response.status === 204) {
    return { success: true, data: null as T };
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiRequestError("PARSE_ERROR", "Invalid JSON response from server.", response.status);
  }

  const envelope = body as ApiResult<T>;

  if (!envelope.success) {
    const err = (envelope as ApiError).error;
    throw new ApiRequestError(err.code, err.message, response.status, err.details);
  }

  return envelope as ApiSuccess<T>;
}

export const api = {
  get: <T>(path: string, init?: RequestInit) =>
    request<T>(path, { ...init, method: "GET" }),

  post: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      ...init,
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      ...init,
      method: "PATCH",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),

  put: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      ...init,
      method: "PUT",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string, init?: RequestInit) =>
    request<T>(path, { ...init, method: "DELETE" }),
};
