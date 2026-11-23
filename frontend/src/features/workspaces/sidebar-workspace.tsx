"use client";

/**
 * Top of the sidebar: which workspace you are in (switch or create one) and that workspace's
 * study rooms, listed like chats so any room is one click away.
 */
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, ChevronsUpDown, LayoutGrid, Plus, Settings2 } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { SubjectDialog } from "@/features/academic/subject-dialog";
import { CreateWorkspaceDialog } from "./create-workspace-dialog";
import {
  notifyRoomsChanged,
  roomHref,
  roomIdFromPath,
  useCurrentWorkspace,
  useRooms,
  workspaceHref,
} from "./current-workspace";

const DEFAULT_COLOUR = "#7c8495";

export function SidebarWorkspace({
  pathname,
  collapsed,
}: {
  pathname: string;
  collapsed: boolean;
}) {
  const router = useRouter();
  const { workspaces, current, reload } = useCurrentWorkspace(pathname);
  const rooms = useRooms(current?.id);
  const [creatingWs, setCreatingWs] = useState(false);
  const [creatingRoom, setCreatingRoom] = useState(false);
  const openRoom = roomIdFromPath(pathname);

  if (!current) return null;
  const colour = current.colour ?? DEFAULT_COLOUR;

  return (
    <div className="space-y-3">
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label={`Workspace: ${current.name}. Switch workspace`}
          className={cn(
            "hover:bg-sidebar-accent/70 focus-visible:ring-ring flex w-full items-center gap-2 rounded-md p-1.5 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none",
            collapsed && "justify-center",
          )}
        >
          <span
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold text-white"
            style={{ backgroundColor: colour }}
            aria-hidden="true"
          >
            {current.name.slice(0, 1).toUpperCase()}
          </span>
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1">
                <span className="text-muted-foreground block text-[11px]">Workspace</span>
                <span className="block truncate text-sm font-semibold">{current.name}</span>
              </span>
              <ChevronsUpDown
                className="text-muted-foreground h-4 w-4 shrink-0"
                aria-hidden="true"
              />
            </>
          )}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-64">
          <DropdownMenuGroup>
            <DropdownMenuLabel>Your workspaces</DropdownMenuLabel>
            {workspaces.map((w) => (
              <DropdownMenuItem key={w.id} onClick={() => router.push(workspaceHref(w.id))}>
                <span
                  className="h-3 w-3 shrink-0 rounded-full"
                  style={{ backgroundColor: w.colour ?? DEFAULT_COLOUR }}
                  aria-hidden="true"
                />
                <span className="flex-1 truncate">{w.name}</span>
                {w.id === current.id ? <Check aria-label="Current" /> : null}
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setCreatingWs(true)}>
            <Plus aria-hidden="true" />
            New workspace
          </DropdownMenuItem>
          <DropdownMenuItem render={<Link href="/workspaces" />}>
            <Settings2 aria-hidden="true" />
            Manage workspaces
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {!collapsed && (
        <section aria-labelledby="rooms-heading">
          <div className="flex items-center justify-between px-1.5">
            <Link
              id="rooms-heading"
              href={workspaceHref(current.id)}
              className="text-muted-foreground hover:text-foreground text-xs font-semibold"
            >
              Study rooms
            </Link>
            <button
              type="button"
              onClick={() => setCreatingRoom(true)}
              aria-label="New study room"
              className="text-muted-foreground hover:bg-sidebar-accent hover:text-foreground focus-visible:ring-ring rounded-md p-1 transition-colors focus-visible:ring-2 focus-visible:outline-none"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
          <ul className="mt-1 max-h-[40vh] space-y-0.5 overflow-y-auto" aria-label="Study rooms">
            {(rooms.data ?? []).map((r) => {
              const active = r.id === openRoom;
              return (
                <li key={r.id}>
                  <Link
                    href={roomHref(current.id, r.id)}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "focus-visible:ring-ring flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none",
                      active
                        ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                        : "text-sidebar-foreground/85 hover:bg-sidebar-accent/60",
                    )}
                  >
                    <span
                      className="flex h-5 w-5 shrink-0 items-center justify-center text-xs"
                      aria-hidden="true"
                    >
                      {r.icon || (
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: r.colour ?? DEFAULT_COLOUR }}
                        />
                      )}
                    </span>
                    <span className="truncate">{r.name}</span>
                  </Link>
                </li>
              );
            })}
            {rooms.data && rooms.data.length === 0 ? (
              <li>
                <button
                  type="button"
                  onClick={() => setCreatingRoom(true)}
                  className="text-muted-foreground hover:text-foreground hover:border-primary/40 w-full rounded-lg border border-dashed px-2 py-2 text-left text-xs transition-colors"
                >
                  + Create your first study room
                </button>
              </li>
            ) : null}
          </ul>
          <Link
            href={workspaceHref(current.id)}
            className="text-muted-foreground hover:text-foreground mt-1 flex items-center gap-2 rounded-lg px-2 py-1 text-xs"
          >
            <LayoutGrid className="h-3.5 w-3.5" aria-hidden="true" />
            All rooms in {current.name}
          </Link>
        </section>
      )}

      <CreateWorkspaceDialog
        open={creatingWs}
        onOpenChange={setCreatingWs}
        onCreated={() => {
          setCreatingWs(false);
          reload();
        }}
      />
      {creatingRoom ? (
        <SubjectDialog
          open={creatingRoom}
          onOpenChange={setCreatingRoom}
          noun="study room"
          workspaceId={current.id}
          onSaved={(s) => {
            setCreatingRoom(false);
            notifyRoomsChanged();
            router.push(roomHref(current.id, s.id));
          }}
        />
      ) : null}
    </div>
  );
}
