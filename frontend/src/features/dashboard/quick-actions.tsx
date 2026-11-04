import Link from "next/link";
import { Activity, Archive, FolderKanban, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

interface QuickActionsProps {
  onCreateWorkspace: () => void;
}

const linkClass =
  "inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Only actions that work today are shown. Subject, folder and chapter creation are added here
 * once their dialogs exist; until then they are not rendered at all (no dead buttons).
 */
export function QuickActions({ onCreateWorkspace }: QuickActionsProps) {
  return (
    <nav aria-label="Quick actions" className="flex flex-wrap gap-2">
      <Button onClick={onCreateWorkspace}>
        <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
        Create workspace
      </Button>
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
