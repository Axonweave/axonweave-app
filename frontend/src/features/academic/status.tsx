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

const DOT: Record<string, string> = {
  not_started: "bg-muted-foreground/40",
  in_progress: "bg-primary",
  completed: "bg-success",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className="text-foreground/80 inline-flex shrink-0 items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-xs font-medium">
      <span
        className={`h-1.5 w-1.5 rounded-full ${DOT[status] ?? DOT.not_started}`}
        aria-hidden="true"
      />
      {statusLabel(status)}
    </span>
  );
}
