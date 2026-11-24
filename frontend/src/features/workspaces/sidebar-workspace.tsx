"use client";

/**
 * Top of the sidebar: your workspaces. Each one opens (like a folder) to show the study rooms
 * inside it, with "New folder" at the end of that list. The + beside the heading creates a
 * workspace; the heading itself opens the page for managing workspaces.
 */
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { ChevronRight, MessagesSquare, Plus } from "lucide-react";
import { environmentHref, makeContext } from "@/lib/learning-context";
import { cn } from "@/lib/utils";
import { SubjectDialog } from "@/features/academic/subject-dialog";
import type { Workspace } from "@/types/api";
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

/** A folder (subject) opens to what is inside it; its study room is a separate action. */
const folderHref = (workspaceId: string, subjectId: string) =>
  environmentHref(makeContext({ workspaceId, subjectId }));

/** Quiet "add" row used for both "New workspace" and "New folder". */
function AddRow({
  label,
  onClick,
  className,
}: {
  label: string;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group text-muted-foreground hover:bg-sidebar-accent hover:text-foreground focus-visible:ring-ring flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-sm transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none",
        className,
      )}
    >
      <span
        className="border-border group-hover:border-foreground/30 group-hover:bg-background flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-dashed transition-all duration-200 group-hover:border-solid"
        aria-hidden="true"
      >
        <Plus className="h-3 w-3 transition-transform duration-200 ease-out group-hover:rotate-90" />
      </span>
      <span className="transition-transform duration-200 ease-out group-hover:translate-x-0.5">
        {label}
      </span>
    </button>
  );
}

function Avatar({ ws, size = "sm" }: { ws: Workspace; size?: "sm" | "md" }) {
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center rounded-md font-semibold text-white",
        size === "sm" ? "h-5 w-5 text-[10px]" : "h-7 w-7 text-xs",
      )}
      style={{ backgroundColor: ws.colour ?? DEFAULT_COLOUR }}
      aria-hidden="true"
    >
      {ws.name.slice(0, 1).toUpperCase()}
    </span>
  );
}

export function SidebarWorkspace({
  pathname,
  collapsed,
}: {
  pathname: string;
  collapsed: boolean;
}) {
  const { workspaces, current, reload } = useCurrentWorkspace(pathname);
  const [creatingWs, setCreatingWs] = useState(false);
  /** Workspaces the learner opened or closed by hand; the current one starts open. */
  const [toggled, setToggled] = useState<Record<string, boolean>>({});

  const dialog = (
    <CreateWorkspaceDialog
      open={creatingWs}
      onOpenChange={setCreatingWs}
      onCreated={() => {
        setCreatingWs(false);
        reload();
      }}
    />
  );

  if (collapsed) {
    return current ? (
      <Link
        href={workspaceHref(current.id)}
        aria-label={`Workspace: ${current.name}`}
        className="hover:bg-sidebar-accent flex justify-center rounded-lg p-1.5 transition-colors"
      >
        <Avatar ws={current} size="md" />
      </Link>
    ) : null;
  }

  return (
    <MotionConfig reducedMotion="user">
      <section aria-labelledby="workspaces-heading">
        <div className="flex items-center justify-between px-1.5">
          <Link
            id="workspaces-heading"
            href="/workspaces"
            className="text-muted-foreground hover:text-foreground text-xs font-medium"
          >
            Workspaces
          </Link>
          <button
            type="button"
            onClick={() => setCreatingWs(true)}
            aria-label="New workspace"
            className="group text-muted-foreground hover:bg-sidebar-accent hover:text-foreground focus-visible:ring-ring rounded-md p-1 transition-colors focus-visible:ring-2 focus-visible:outline-none"
          >
            <Plus
              className="h-3.5 w-3.5 transition-transform duration-200 ease-out group-hover:rotate-90"
              aria-hidden="true"
            />
          </button>
        </div>

        <ul className="mt-1.5 max-h-[50vh] space-y-0.5 overflow-y-auto" aria-label="Workspaces">
          {workspaces.map((w) => (
            <WorkspaceItem
              key={w.id}
              ws={w}
              pathname={pathname}
              open={toggled[w.id] ?? w.id === current?.id}
              onToggle={(v) => setToggled((t) => ({ ...t, [w.id]: v }))}
            />
          ))}
          {workspaces.length === 0 ? (
            <li>
              <AddRow label="New workspace" onClick={() => setCreatingWs(true)} />
            </li>
          ) : null}
        </ul>
      </section>
      {dialog}
    </MotionConfig>
  );
}

function WorkspaceItem({
  ws,
  pathname,
  open,
  onToggle,
}: {
  ws: Workspace;
  pathname: string;
  open: boolean;
  onToggle: (open: boolean) => void;
}) {
  const here = pathname === workspaceHref(ws.id);
  const listId = `ws-rooms-${ws.id}`;
  return (
    <li>
      <div
        className={cn(
          "group/ws flex items-center rounded-lg transition-colors duration-150",
          here ? "bg-sidebar-accent" : "hover:bg-sidebar-accent/60",
        )}
      >
        <button
          type="button"
          onClick={() => onToggle(!open)}
          aria-expanded={open}
          aria-controls={listId}
          aria-label={`${open ? "Close" : "Open"} ${ws.name}`}
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring ml-0.5 rounded-md p-1 focus-visible:ring-2 focus-visible:outline-none"
        >
          <ChevronRight
            className={cn(
              "h-3.5 w-3.5 transition-transform duration-200 ease-out",
              open && "rotate-90",
            )}
            aria-hidden="true"
          />
        </button>
        <Link
          href={workspaceHref(ws.id)}
          aria-current={here ? "page" : undefined}
          className={cn(
            "focus-visible:ring-ring flex min-w-0 flex-1 items-center gap-2 rounded-lg py-1.5 pr-2 pl-0.5 text-sm focus-visible:ring-2 focus-visible:outline-none",
            here ? "text-foreground font-medium" : "text-sidebar-foreground",
          )}
        >
          <span className="transition-transform duration-200 group-hover/ws:scale-110">
            <Avatar ws={ws} />
          </span>
          <span className="truncate font-medium">{ws.name}</span>
        </Link>
      </div>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            id={listId}
            key="rooms"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <WorkspaceRooms ws={ws} pathname={pathname} />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </li>
  );
}

function WorkspaceRooms({ ws, pathname }: { ws: Workspace; pathname: string }) {
  const router = useRouter();
  const rooms = useRooms(ws.id);
  const [creating, setCreating] = useState(false);
  const openRoom = roomIdFromPath(pathname);

  return (
    <div className="border-border mt-0.5 mb-1 ml-[15px] border-l pl-2">
      <ul className="space-y-0.5" aria-label={`Folders in ${ws.name}`}>
        {(rooms.data ?? []).map((r, i) => {
          const active = r.id === openRoom;
          return (
            <motion.li
              key={r.id}
              className="group/row relative"
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03, duration: 0.2 }}
            >
              <Link
                href={folderHref(ws.id, r.id)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group focus-visible:ring-ring flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none",
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
                      className="h-2 w-2 rounded-full transition-transform duration-200 group-hover:scale-125"
                      style={{ backgroundColor: r.colour ?? DEFAULT_COLOUR }}
                    />
                  )}
                </span>
                <span className="truncate pr-6 transition-transform duration-200 ease-out group-hover:translate-x-0.5">
                  {r.name}
                </span>
              </Link>
              <Link
                href={roomHref(ws.id, r.id)}
                aria-label={`Open study room for ${r.name}`}
                title="Open study room"
                className="text-muted-foreground hover:bg-background hover:text-foreground focus-visible:ring-ring absolute top-1/2 right-1 -translate-y-1/2 rounded-md p-1 opacity-0 transition-opacity group-focus-within/row:opacity-100 group-hover/row:opacity-100 focus-visible:ring-2 focus-visible:outline-none"
              >
                <MessagesSquare className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </motion.li>
          );
        })}
        <li>
          <AddRow label="New folder" onClick={() => setCreating(true)} />
        </li>
      </ul>
      {creating ? (
        <SubjectDialog
          open={creating}
          onOpenChange={setCreating}
          noun="folder"
          workspaceId={ws.id}
          onSaved={(s) => {
            setCreating(false);
            notifyRoomsChanged();
            router.push(folderHref(ws.id, s.id));
          }}
        />
      ) : null}
    </div>
  );
}
