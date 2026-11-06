import { api } from "./client";

export interface Paged<T> {
  data: T[];
  total: number;
}

/**
 * List endpoints answer { success, data: [...], total } so the client's `data` is the array and
 * `total` sits beside it. Re-read the raw envelope for those via this helper.
 */
export async function getPaged<T>(path: string): Promise<Paged<T>> {
  const res = await api.get<T[]>(path);
  const total = (res as unknown as { total?: number }).total ?? res.data.length;
  return { data: res.data, total };
}

/** Builds "?a=1&b=2" from defined values only; values are URL-encoded. */
export function query(
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
