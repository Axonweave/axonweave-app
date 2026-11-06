import type { ChapterStatus } from "@/types/api";

/**
 * Chapter status is an organisational label the person sets themselves. It is not a measure of
 * understanding or mastery and nothing here should be worded as if it were.
 */
export const STATUS_OPTIONS: Array<{ value: ChapterStatus; label: string }> = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
];

export function statusLabel(status: string): string {
  return STATUS_OPTIONS.find((s) => s.value === status)?.label ?? status;
}

const STYLES: Record<string, string> = {
  not_started: "bg-muted text-muted-foreground",
  in_progress: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
  completed: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        STYLES[status] ?? STYLES.not_started
      }`}
    >
      {statusLabel(status)}
    </span>
  );
}
