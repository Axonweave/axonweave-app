import { STATUS_LABELS, errorText, isTerminal } from "@/lib/api/documents";

const TONE: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  failed: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
  cancelled: "bg-muted text-muted-foreground",
};

/** Status chip. Text, not colour alone, carries the meaning (accessibility). */
export function StatusBadge({ status }: { status: string }) {
  const tone = TONE[status] ?? "bg-blue-100 text-blue-900 dark:bg-blue-950 dark:text-blue-200";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}
      aria-busy={!isTerminal(status)}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

export { errorText };

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
