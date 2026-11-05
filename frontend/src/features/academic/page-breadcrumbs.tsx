import Link from "next/link";
import { ChevronRight } from "lucide-react";

export interface Crumb {
  label: string;
  /** Omit for the current page and for crumbs that have no page of their own. */
  href?: string;
}

/** In-page breadcrumb trail. The last crumb is the current page. */
export function PageBreadcrumbs({ crumbs }: { crumbs: Crumb[] }) {
  return (
    <nav aria-label="You are here" className="min-w-0">
      <ol className="text-muted-foreground flex flex-wrap items-center gap-1 text-sm">
        {crumbs.map((crumb, i) => {
          const last = i === crumbs.length - 1;
          return (
            <li key={`${crumb.label}-${i}`} className="flex min-w-0 items-center gap-1">
              {i > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              {crumb.href && !last ? (
                <Link
                  href={crumb.href}
                  className="hover:text-foreground focus-visible:ring-ring truncate rounded-sm underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span
                  className={`truncate ${last ? "text-foreground font-medium" : ""}`}
                  aria-current={last ? "page" : undefined}
                >
                  {crumb.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
