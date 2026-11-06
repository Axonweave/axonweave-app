import Link from "next/link";
import { Activity, Archive, BookOpen, BookPlus, FolderKanban, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

interface QuickActionsProps {
  onCreateWorkspace: () => void;
}

const linkClass =
  "inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Only actions that work are shown. Folders and chapters are created inside a subject page, so
 * the subject links are the way in.
 */
export function QuickActions({ onCreateWorkspace }: QuickActionsProps) {
  return (
    <nav aria-label="Quick actions" className="flex flex-wrap gap-2">
      <Button onClick={onCreateWorkspace}>
        <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
        Create workspace
      </Button>
      <Link href="/subjects?create=1" className={linkClass}>
        <BookPlus className="h-4 w-4" aria-hidden="true" />
        New subject
      </Link>
      <Link href="/subjects" className={linkClass}>
        <BookOpen className="h-4 w-4" aria-hidden="true" />
        Browse subjects
      </Link>
      <Link href="/workspaces" className={linkClass}>
        <FolderKanban className="h-4 w-4" aria-hidden="true" />
        All workspaces
      </Link>
      <Link href="/activity" className={linkClass}>
        <Activity className="h-4 w-4" aria-hidden="true" />
        Recent activity
      </Link>
      <Link href="/archived" className={linkClass}>
        <Archive className="h-4 w-4" aria-hidden="true" />
        Archived items
      </Link>
    </nav>
  );
}
