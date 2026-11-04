import { ArchivedList } from "@/features/archived/archived-list";

export default function ArchivedPage() {
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Archived items</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Restore archived workspaces, subjects, folders and chapters, or delete them permanently.
        </p>
      </div>
      <ArchivedList />
    </div>
  );
}
