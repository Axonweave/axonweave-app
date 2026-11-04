import Link from "next/link";
import { activityHref, describeActivity, formatDateTime } from "@/lib/activity";
import type { ActivityItem } from "@/types/api";

const linkClass =
  "rounded-sm font-medium text-foreground underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function ActivityList({ items }: { items: ActivityItem[] }) {
  return (
    <ul className="divide-border border-border divide-y rounded-lg border">
      {items.map((item) => {
        const href = activityHref(item);
        const sentence = describeActivity(item);
        return (
          <li
            key={item.id}
            className="flex flex-col gap-1 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
          >
            <span className="min-w-0 break-words">
              {href ? (
                <Link href={href} className={linkClass}>
                  {sentence}
                </Link>
              ) : (
                <span>{sentence}</span>
              )}
              {item.entity_status === "archived" && (
                <span className="text-muted-foreground ml-2 text-xs">(archived)</span>
              )}
              {item.entity_status === "deleted" && item.action !== "deleted" && (
                <span className="text-muted-foreground ml-2 text-xs">(no longer exists)</span>
              )}
            </span>
            <time dateTime={item.created_at} className="text-muted-foreground shrink-0 text-xs">
              {formatDateTime(item.created_at)}
            </time>
          </li>
        );
      })}
    </ul>
  );
}
