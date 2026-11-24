"use client";

/**
 * A workspace's home: its study rooms as cards. Each room (a subject in the API) is where the
 * learner chats, uploads and uses every tool; this page is just the way in.
 */
import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowRight, FolderTree, MoreHorizontal, Pencil, Plus } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorDisplay } from "@/components/ui/error-display";
import { useAsync } from "@/hooks/use-async";
import { ApiRequestError } from "@/lib/api/client";
import { workspacesApi } from "@/lib/api/workspaces";
import { cn } from "@/lib/utils";
import { SubjectDialog } from "@/features/academic/subject-dialog";
import { environmentHref, makeContext } from "@/lib/learning-context";
import { notifyRoomsChanged, roomHref, useRooms } from "./current-workspace";
import type { Subject } from "@/types/api";

const DEFAULT_COLOUR = "#6366f1";

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  const m = s / 60;
  if (m < 60) return `${Math.floor(m)} min ago`;
  const h = m / 60;
  if (h < 24) return `${Math.floor(h)} h ago`;
  const d = h / 24;
  if (d < 30) return `${Math.floor(d)} d ago`;
  return new Date(iso).toLocaleDateString();
}

export function WorkspaceHome() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const router = useRouter();
  const ws = useAsync(
    () =>
      workspacesApi
        .get(workspaceId)
        .then((r) => r.data)
        .catch((e: unknown) => {
          if (e instanceof ApiRequestError && e.status === 404) return null;
          throw e;
        }),
    [workspaceId],
  );
  const rooms = useRooms(workspaceId);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Subject | null>(null);

  if (ws.error)
    return <ErrorDisplay message="Could not load this workspace." onRetry={ws.reload} />;
  if (!ws.loading && ws.data === null)
    return (
      <EmptyState
        title="Workspace not found"
        description="It may have been deleted, or it isn't yours."
        action={
          <Link href="/workspaces" className={buttonVariants()}>
            All workspaces
          </Link>
        }
      />
    );

  const workspace = ws.data;
  const colour = workspace?.colour ?? DEFAULT_COLOUR;
  const list = rooms.data ?? [];

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <header className="animate-in fade-in-0 border-b pb-6 duration-300">
        <p className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
          <span
            className="h-2 w-2 rounded-full"
            style={{ backgroundColor: colour }}
            aria-hidden="true"
          />
          Workspace
        </p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight break-words">
              {workspace?.name ?? " "}
            </h1>
            {workspace?.description ? (
              <p className="text-muted-foreground mt-1 max-w-2xl text-sm">
                {workspace.description}
              </p>
            ) : null}
            <p className="text-muted-foreground mt-2 text-sm">
              {rooms.data
                ? `${list.length} ${list.length === 1 ? "folder" : "folders"}`
                : "Loading folders…"}
            </p>
          </div>
          <Button onClick={() => setCreating(true)}>
            <Plus aria-hidden="true" />
            New folder
          </Button>
        </div>
      </header>

      {rooms.error ? (
        <ErrorDisplay message="Could not load the folders." onRetry={rooms.reload} />
      ) : !rooms.data ? (
        <RoomSkeletons />
      ) : list.length === 0 ? (
        <EmptyState
          title="No folders yet"
          description="A folder holds everything for one subject or chapter: your files, chats with the AI Tutor, flashcards, quizzes and progress."
          action={<Button onClick={() => setCreating(true)}>Create a folder</Button>}
        />
      ) : (
        <section aria-labelledby="rooms-grid">
          <h2 id="rooms-grid" className="mb-3 text-base font-semibold tracking-tight">
            Folders
          </h2>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {list.map((r, i) => (
              <RoomCard
                key={r.id}
                room={r}
                index={i}
                workspaceId={workspaceId}
                onEdit={() => setEditing(r)}
              />
            ))}
            <li>
              <button
                type="button"
                onClick={() => setCreating(true)}
                className="text-muted-foreground hover:text-foreground hover:bg-muted/40 focus-visible:ring-ring flex h-full min-h-36 w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed transition-colors focus-visible:ring-2 focus-visible:outline-none"
              >
                <Plus className="h-6 w-6" aria-hidden="true" />
                <span className="text-sm font-medium">New folder</span>
              </button>
            </li>
          </ul>
          <p className="text-muted-foreground mt-4 text-sm">
            Looking for an archived folder?{" "}
            <Link
              href={`/subjects?workspace=${workspaceId}`}
              className="text-primary font-medium hover:underline"
            >
              Manage all folders
            </Link>
          </p>
        </section>
      )}

      {creating ? (
        <SubjectDialog
          open={creating}
          onOpenChange={setCreating}
          workspaceId={workspaceId}
          noun="folder"
          onSaved={(s) => {
            setCreating(false);
            notifyRoomsChanged();
            router.push(roomHref(workspaceId, s.id));
          }}
        />
      ) : null}
      {editing ? (
        <SubjectDialog
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          workspaceId={workspaceId}
          subject={editing}
          noun="folder"
          onSaved={() => {
            setEditing(null);
            notifyRoomsChanged();
          }}
        />
      ) : null}
    </div>
  );
}

function RoomCard({
  room,
  index,
  workspaceId,
  onEdit,
}: {
  room: Subject;
  index: number;
  workspaceId: string;
  onEdit: () => void;
}) {
  const colour = room.colour ?? DEFAULT_COLOUR;
  return (
    <li
      className="animate-in fade-in-0 fill-mode-both duration-300"
      style={{ animationDelay: `${Math.min(index, 8) * 30}ms` }}
    >
      <div className="group bg-card hover:bg-muted/30 hover:border-foreground/20 relative flex h-full flex-col rounded-lg border transition-colors">
        <div className="flex flex-1 flex-col p-4">
          <span
            className="bg-background flex h-9 w-9 items-center justify-center rounded-md border text-base"
            aria-hidden="true"
          >
            {room.icon || (
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colour }} />
            )}
          </span>
          <Link
            href={roomHref(workspaceId, room.id)}
            className="mt-3 font-semibold tracking-tight after:absolute after:inset-0 after:rounded-lg focus-visible:outline-none"
          >
            {room.name}
          </Link>
          <p className="text-muted-foreground mt-1 line-clamp-2 flex-1 text-sm">
            {room.description || "Chat, files, flashcards, quizzes and progress in one place."}
          </p>
          <div className="text-muted-foreground mt-3 flex items-center justify-between text-xs">
            <span>Updated {timeAgo(room.updated_at)}</span>
            <span className="text-primary inline-flex items-center gap-1 font-medium opacity-0 transition-opacity group-hover:opacity-100">
              Open <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </span>
          </div>
        </div>
        <div className="absolute top-2 right-2 z-10">
          <DropdownMenu>
            <DropdownMenuTrigger
              aria-label={`${room.name} options`}
              className={cn(
                "text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring rounded-md p-1.5 transition-colors focus-visible:ring-2 focus-visible:outline-none",
              )}
            >
              <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-52">
              <DropdownMenuItem onClick={onEdit}>
                <Pencil aria-hidden="true" />
                Rename or recolour
              </DropdownMenuItem>
              <DropdownMenuItem
                render={
                  <Link
                    href={environmentHref(
                      makeContext({ workspaceId, subjectId: room.id }),
                      "content",
                    )}
                  />
                }
              >
                <FolderTree aria-hidden="true" />
                Chapters, archive and delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </li>
  );
}

function RoomSkeletons() {
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Loading folders">
      {[0, 1, 2].map((i) => (
        <li key={i} className="bg-muted/60 h-36 animate-pulse rounded-lg" />
      ))}
    </ul>
  );
}
