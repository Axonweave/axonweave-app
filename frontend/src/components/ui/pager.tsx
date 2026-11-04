import { Button } from "@/components/ui/button";

interface PagerProps {
  offset: number;
  limit: number;
  total: number;
  onChange: (offset: number) => void;
}

/** Previous/Next controls with a "Showing a–b of n" summary. */
export function Pager({ offset, limit, total, onChange }: PagerProps) {
  if (total <= limit) return null;
  const from = offset + 1;
  const to = Math.min(offset + limit, total);

  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-2">
      <p className="text-muted-foreground text-sm" aria-live="polite">
        Showing {from}–{to} of {total}
      </p>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
        >
          Next
        </Button>
      </div>
    </nav>
  );
}
