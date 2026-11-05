import { ApiRequestError } from "@/lib/api/client";

/** Same look as the select on the workspaces form. */
export const SELECT_CLASS =
  "border-input bg-background focus:ring-ring w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:outline-none";

export const TEXTAREA_CLASS =
  "border-input bg-background focus:ring-ring min-h-20 w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:outline-none";

/** The server's own message when it sent one (names, depth, conflicts), else a generic line. */
export function errorMessage(err: unknown, fallback = "Something went wrong. Please try again."): string {
  return err instanceof ApiRequestError ? err.message : fallback;
}

/** Visible, announced form-level error. */
export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="bg-destructive/10 text-destructive rounded-md px-3 py-2 text-sm"
    >
      {message}
    </div>
  );
}

/** Indents a folder name by its depth for use inside a native <option>. */
export function indented(label: string, depth: number): string {
  return `${"  ".repeat(Math.max(0, depth - 1))}${depth > 0 ? "↳ " : ""}${label}`;
}
