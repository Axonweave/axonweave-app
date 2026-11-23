"use client";

import Link from "next/link";
import { ArrowUpRight, BookOpen, FileText, Folder as FolderIcon } from "lucide-react";
import { SCOPE_LABELS, environmentBase, environmentHref } from "@/lib/learning-context";
import { cn } from "@/lib/utils";
import { useRecentContexts } from "./use-recent-contexts";

const ICONS = { workspace: BookOpen, subject: BookOpen, folder: FolderIcon, chapter: FileText };

/**
 * The learning space the learner is in (or was last in), one click away from anywhere. Read from
 * this browser's recent list; shows nothing until a subject, folder or chapter has been opened.
 */
export function CurrentSpaceCard({ pathname }: { pathname: string }) {
  const [latest] = useRecentContexts();
  if (!latest) return null;
  const base = environmentBase(latest.ctx);
  const inside = !!base && (pathname === base || pathname.startsWith(`${base}/`));
  const Icon = ICONS[latest.ctx.scope];

  return (
    <Link
      href={environmentHref(latest.ctx)}
      className={cn(
        "group border-border hover:bg-accent/50 focus-visible:ring-ring block rounded-lg border p-2 transition-colors focus-visible:ring-2 focus-visible:outline-none",
        inside && "bg-accent/40",
      )}
      style={latest.colour ? { borderLeftColor: latest.colour, borderLeftWidth: 3 } : undefined}
    >
      <span className="text-muted-foreground flex items-center justify-between text-[10px] font-semibold tracking-widest uppercase">
        {inside ? "You are in" : "Continue in"}
        <ArrowUpRight
          className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100"
          aria-hidden="true"
        />
      </span>
      <span className="mt-1 flex items-center gap-1.5 text-sm font-medium">
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="truncate">{latest.label}</span>
      </span>
      <span className="text-muted-foreground block truncate text-xs">
        {SCOPE_LABELS[latest.ctx.scope]} · {latest.trail}
      </span>
    </Link>
  );
}
