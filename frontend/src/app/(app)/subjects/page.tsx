"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Archive, ArchiveRestore, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorDisplay } from "@/components/ui/error-display";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/ui/loading";
import { Pager } from "@/components/ui/pager";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import { chaptersApi } from "@/lib/api/chapters";
import { foldersApi } from "@/lib/api/folders";
import { subjectsApi, type SubjectSortField } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";
import { DestructiveDialog } from "@/features/academic/destructive-dialog";
import { SELECT_CLASS } from "@/features/academic/form-bits";
import { RowActions } from "@/features/academic/row-actions";
import { SubjectDialog } from "@/features/academic/subject-dialog";
import type { Subject } from "@/types/api";

const PAGE_SIZE = 12;

const SORTS: { value: string; label: string; by: SubjectSortField; dir: "asc" | "desc" }[] = [
  { value: "updated_desc", label: "Recently updated", by: "updated_at", dir: "desc" },
  { value: "name_asc", label: "Name (A–Z)", by: "name", dir: "asc" },
  { value: "name_desc", label: "Name (Z–A)", by: "name", dir: "desc" },
];

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

function SubjectsView() {
  const router = useRouter();
  const params = useSearchParams();
  const { toast } = useToast();

  const workspaceParam = params.get("workspace");
  const createParam = params.get("create") === "1";

  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [sort, setSort] = useState(SORTS[0].value);
  const [offset, setOffset] = useState(0);
  const [showArchived, setShowArchived] = useState(false);
  const [createOpen, setCreateOpen] = useState(createParam);
  const [editing, setEditing] = useState<Subject | null>(null);
  const [deleting, setDeleting] = useState<{
    subject: Subject;
    folders: number;
    chapters: number;
  } | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedQ(q.trim());
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  const workspaces = useAsync(() => workspacesApi.list(false).then((r) => r.data), []);
  const list = workspaces.data ?? [];
  const workspaceId =
    (workspaceParam && list.find((w) => w.id === workspaceParam)?.id) ??
    list.find((w) => w.is_default)?.id ??
    list[0]?.id ??
    null;

  const sortDef = SORTS.find((s) => s.value === sort) ?? SORTS[0];

  const subjects = useAsync(
    async () =>
      workspaceId
        ? subjectsApi.list(workspaceId, {
            q: debouncedQ || undefined,
            sortBy: sortDef.by,
            sortDir: sortDef.dir,
            limit: PAGE_SIZE,
            offset,
            includeArchived: showArchived,
          })
        : null,
    [workspaceId, debouncedQ, sortDef.by, sortDef.dir, offset, showArchived],
  );

  const pickWorkspace = (id: string) => {
    setOffset(0);
    router.replace(`/subjects?workspace=${id}`);
  };

  const closeCreate = () => {
    setCreateOpen(false);
    if (createParam)
      router.replace(workspaceId ? `/subjects?workspace=${workspaceId}` : "/subjects");
  };

  const failure = (title: string, err: unknown) =>
    toast({
      title,
      description: err instanceof ApiRequestError ? err.message : undefined,
      variant: "destructive",
    });

  const archive = async (s: Subject) => {
    if (!workspaceId) return;
    try {
      await subjectsApi.archive(workspaceId, s.id);
      toast({ title: `Subject “${s.name}” archived` });
      subjects.reload();
    } catch (err) {
      failure("Could not archive subject", err);
    }
  };

  const restore = async (s: Subject) => {
    if (!workspaceId) return;
    try {
      await subjectsApi.restore(workspaceId, s.id);
      toast({ title: `Subject “${s.name}” restored` });
      subjects.reload();
    } catch (err) {
      failure("Could not restore subject", err);
    }
  };

  const askDelete = async (s: Subject) => {
    if (!workspaceId) return;
    try {
      const [folders, chapters] = await Promise.all([
        foldersApi.listAll(workspaceId, s.id),
        chaptersApi.list(workspaceId, s.id, { limit: 1 }),
      ]);
      setDeleting({ subject: s, folders: folders.length, chapters: chapters.total });
    } catch (err) {
      failure("Could not load what this subject contains", err);
    }
  };

  if (workspaces.loading && !workspaces.data) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center" aria-busy="true">
        <LoadingSpinner />
      </div>
    );
  }
  if (workspaces.error) {
    return <ErrorDisplay message={workspaces.error} onRetry={workspaces.reload} />;
  }
  if (!workspaceId) {
    return (
      <EmptyState
        title="Create a workspace first"
        description="Subjects live inside a workspace."
        action={
          <Link href="/workspaces" className="text-primary underline underline-offset-4">
            Go to workspaces
          </Link>
        }
      />
    );
  }

  const result = subjects.data;
  const rows = result?.data ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Subjects</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            The topics you study. Each holds folders and chapters.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
          New subject
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-1">
          <label htmlFor="subjects-workspace" className="text-sm font-medium">
            Workspace
          </label>
          <select
            id="subjects-workspace"
            value={workspaceId}
            onChange={(e) => pickWorkspace(e.target.value)}
            className={SELECT_CLASS}
          >
            {list.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="subjects-search" className="text-sm font-medium">
            Search
          </label>
          <div className="relative">
            <Search
              className="text-muted-foreground pointer-events-none absolute top-2.5 left-2.5 h-4 w-4"
              aria-hidden="true"
            />
            <Input
              id="subjects-search"
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name"
              className="pl-8"
              maxLength={255}
            />
          </div>
        </div>
        <div className="space-y-1">
          <label htmlFor="subjects-sort" className="text-sm font-medium">
            Sort by
          </label>
          <select
            id="subjects-sort"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setOffset(0);
            }}
            className={SELECT_CLASS}
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <label className="flex w-fit items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={showArchived}
          onChange={(e) => {
            setShowArchived(e.target.checked);
            setOffset(0);
          }}
          className="h-4 w-4"
        />
        Show archived
      </label>

      {subjects.error ? (
        <ErrorDisplay message={subjects.error} onRetry={subjects.reload} />
      ) : !result ? (
        <div className="flex min-h-[20vh] items-center justify-center" aria-busy="true">
          <LoadingSpinner />
        </div>
      ) : rows.length === 0 ? (
        debouncedQ ? (
          <EmptyState
            title="No subjects match"
            description={`Nothing in this workspace is named like “${debouncedQ}”.`}
          />
        ) : (
          <EmptyState
            title={showArchived ? "No subjects yet" : "No subjects yet"}
            description="Create your first subject to start organising folders and chapters."
            action={<Button onClick={() => setCreateOpen(true)}>Create subject</Button>}
          />
        )
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Subjects">
          {rows.map((s) => {
            const archived = !!s.archived_at;
            return (
              <li
                key={s.id}
                className={`border-border flex items-start gap-3 rounded-lg border p-4 ${
                  archived ? "opacity-70" : ""
                }`}
              >
                <span
                  className="mt-1.5 h-3 w-3 shrink-0 rounded-full"
                  style={{ backgroundColor: s.colour ?? "#6b7280" }}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <Link
                    href={`/workspaces/${workspaceId}/subjects/${s.id}`}
                    className="focus-visible:ring-ring block truncate rounded-sm font-medium underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
                  >
                    {s.icon ? `${s.icon} ` : ""}
                    {s.name}
                  </Link>
                  {s.description && (
                    <p className="text-muted-foreground mt-0.5 line-clamp-2 text-sm">
                      {s.description}
                    </p>
                  )}
                  {archived && (
                    <span className="bg-muted text-muted-foreground mt-1 inline-block rounded-full px-2 py-0.5 text-xs">
                      Archived
                    </span>
                  )}
                </div>
                <RowActions
                  name={`subject ${s.name}`}
                  actions={
                    archived
                      ? [
                          {
                            label: "Restore",
                            icon: <ArchiveRestore />,
                            onSelect: () => restore(s),
                          },
                          {
                            label: "Delete",
                            icon: <Trash2 />,
                            destructive: true,
                            separated: true,
                            onSelect: () => askDelete(s),
                          },
                        ]
                      : [
                          { label: "Edit", icon: <Pencil />, onSelect: () => setEditing(s) },
                          { label: "Archive", icon: <Archive />, onSelect: () => archive(s) },
                          {
                            label: "Delete",
                            icon: <Trash2 />,
                            destructive: true,
                            separated: true,
                            onSelect: () => askDelete(s),
                          },
                        ]
                  }
                />
              </li>
            );
          })}
        </ul>
      )}

      {result && (
        <Pager offset={offset} limit={PAGE_SIZE} total={result.total} onChange={setOffset} />
      )}

      <SubjectDialog
        open={createOpen}
        onOpenChange={(o) => !o && closeCreate()}
        workspaceId={workspaceId}
        onSaved={(s) => {
          closeCreate();
          toast({ title: `Subject “${s.name}” created` });
          subjects.reload();
        }}
      />

      {editing && (
        <SubjectDialog
          open
          onOpenChange={(o) => !o && setEditing(null)}
          workspaceId={workspaceId}
          subject={editing}
          onSaved={() => {
            setEditing(null);
            toast({ title: "Subject updated" });
            subjects.reload();
          }}
        />
      )}

      {deleting && (
        <DestructiveDialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          title={`Delete subject “${deleting.subject.name}”?`}
          description={
            <p>
              This permanently deletes the subject and everything in it:{" "}
              <strong>
                {plural(deleting.folders, "folder", "folders")} and{" "}
                {plural(deleting.chapters, "chapter", "chapters")}
              </strong>
              . It cannot be undone. To keep it but hide it, archive it instead.
            </p>
          }
          confirmLabel="Delete subject"
          requireText={deleting.subject.name}
          onConfirm={async () => {
            await subjectsApi.remove(workspaceId, deleting.subject.id);
            toast({ title: `Subject “${deleting.subject.name}” deleted` });
            setDeleting(null);
            subjects.reload();
          }}
        />
      )}
    </div>
  );
}

export default function SubjectsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center" aria-busy="true">
          <LoadingSpinner />
        </div>
      }
    >
      <SubjectsView />
    </Suspense>
  );
}
