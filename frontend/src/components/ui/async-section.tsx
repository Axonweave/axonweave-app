import type { ReactNode } from "react";
import { ErrorDisplay } from "@/components/ui/error-display";
import { LoadingSpinner } from "@/components/ui/loading";

interface AsyncSectionProps {
  /** Visible heading; also labels the region for assistive tech. */
  title: string;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
  isEmpty: boolean;
  empty: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}

/** One dashboard section with consistent loading, error and empty states. */
export function AsyncSection({
  title,
  loading,
  error,
  onRetry,
  isEmpty,
  empty,
  action,
  children,
}: AsyncSectionProps) {
  const headingId = `section-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  let body: ReactNode;
  if (loading) {
    body = (
      <div className="flex min-h-[120px] items-center justify-center" aria-busy="true">
        <LoadingSpinner />
      </div>
    );
  } else if (error) {
    body = <ErrorDisplay title="Could not load" message={error} onRetry={onRetry} />;
  } else if (isEmpty) {
    body = empty;
  } else {
    body = children;
  }

  return (
    <section aria-labelledby={headingId} className="min-w-0 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 id={headingId} className="text-foreground text-lg font-semibold">
          {title}
        </h2>
        {action}
      </div>
      {body}
    </section>
  );
}
