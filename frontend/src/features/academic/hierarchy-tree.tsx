"use client";

import Link from "next/link";
import {
  Archive,
  ArrowDown,
  ArrowUp,
  FileText,
  Folder as FolderIcon,
  FolderInput,
  FolderPlus,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Chapter, Folder } from "@/types/api";
import { RowActions } from "./row-actions";
import { StatusBadge } from "./status";
import { MAX_FOLDER_DEPTH, reorderedIds, type FolderNode, type Hierarchy } from "./tree";

export interface TreeActions {
  onAddSubfolder: (folder: Folder) => void;
  onAddChapter: (folderId: string | null) => void;
  onEditFolder: (folder: Folder) => void;
  onMoveFolder: (folder: Folder) => void;
  onArchiveFolder: (folder: Folder) => void;
  onDeleteFolder: (folder: Folder) => void;
  onEditChapter: (chapter: Chapter) => void;
  onMoveChapter: (chapter: Chapter) => void;
  onArchiveChapter: (chapter: Chapter) => void;
  onDeleteChapter: (chapter: Chapter) => void;
  onReorder: (chapter: Chapter, direction: "up" | "down") => void;
}

interface TreeProps {
  workspaceId: string;
  subjectId: string;
  hierarchy: Hierarchy;
  /** Every chapter of the subject, used to know whether a chapter can still move up or down. */
  chapters: Chapter[];
  actions: TreeActions;
}

function ChapterRow({
  chapter,
  workspaceId,
  subjectId,
  chapters,
  actions,
}: { chapter: Chapter } & Omit<TreeProps, "hierarchy">) {
  const canUp = reorderedIds(chapters, chapter.id, "up") !== null;
  const canDown = reorderedIds(chapters, chapter.id, "down") !== null;
  return (
    <li className="border-border flex flex-wrap items-center gap-2 rounded-md border px-3 py-2">
      <FileText className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden="true" />
      <Link
        href={`/workspaces/${workspaceId}/subjects/${subjectId}/chapters/${chapter.id}`}
        className="focus-visible:ring-ring min-w-0 flex-1 truncate rounded-sm font-medium underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
      >
        {chapter.title}
      </Link>
      <StatusBadge status={chapter.status} />
      <div className="flex items-center">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          id={`move-${chapter.id}-up`}
          disabled={!canUp}
          onClick={() => actions.onReorder(chapter, "up")}
          aria-label={`Move chapter ${chapter.title} up`}
        >
          <ArrowUp className="h-4 w-4" aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          id={`move-${chapter.id}-down`}
          disabled={!canDown}
          onClick={() => actions.onReorder(chapter, "down")}
          aria-label={`Move chapter ${chapter.title} down`}
        >
          <ArrowDown className="h-4 w-4" aria-hidden="true" />
        </Button>
        <RowActions
          name={`chapter ${chapter.title}`}
          actions={[
            { label: "Edit", icon: <Pencil />, onSelect: () => actions.onEditChapter(chapter) },
            {
              label: "Move to folder…",
              icon: <FolderInput />,
              onSelect: () => actions.onMoveChapter(chapter),
            },
            {
              label: "Archive",
              icon: <Archive />,
              onSelect: () => actions.onArchiveChapter(chapter),
            },
            {
              label: "Delete",
              icon: <Trash2 />,
              destructive: true,
              separated: true,
              onSelect: () => actions.onDeleteChapter(chapter),
            },
          ]}
        />
      </div>
    </li>
  );
}

function FolderBlock({ node, ...rest }: { node: FolderNode } & Omit<TreeProps, "hierarchy">) {
  const { folder } = node;
  const { actions } = rest;
  const canNest = node.depth < MAX_FOLDER_DEPTH;
  return (
    <li className="space-y-2">
      <div className="bg-muted/40 flex flex-wrap items-center gap-2 rounded-md px-3 py-2">
        <FolderIcon className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{folder.name}</p>
          {folder.description && (
            <p className="text-muted-foreground line-clamp-1 text-xs">{folder.description}</p>
          )}
        </div>
        <RowActions
          name={`folder ${folder.name}`}
          actions={[
            {
              label: "Add chapter here",
              icon: <Plus />,
              onSelect: () => actions.onAddChapter(folder.id),
            },
            ...(canNest
              ? [
                  {
                    label: "Add subfolder",
                    icon: <FolderPlus />,
                    onSelect: () => actions.onAddSubfolder(folder),
                  },
                ]
              : []),
            { label: "Edit", icon: <Pencil />, onSelect: () => actions.onEditFolder(folder) },
            {
              label: "Move…",
              icon: <FolderInput />,
              onSelect: () => actions.onMoveFolder(folder),
            },
            {
              label: "Archive",
              icon: <Archive />,
              onSelect: () => actions.onArchiveFolder(folder),
            },
            {
              label: "Delete",
              icon: <Trash2 />,
              destructive: true,
              separated: true,
              onSelect: () => actions.onDeleteFolder(folder),
            },
          ]}
        />
      </div>
      {(node.children.length > 0 || node.chapters.length > 0) && (
        <ul className="border-border ml-3 space-y-2 border-l pl-3 sm:ml-4 sm:pl-4">
          {node.chapters.map((c) => (
            <ChapterRow key={c.id} chapter={c} {...rest} />
          ))}
          {node.children.map((child) => (
            <FolderBlock key={child.folder.id} node={child} {...rest} />
          ))}
        </ul>
      )}
    </li>
  );
}

/** The folder and chapter hierarchy of one subject. */
export function HierarchyTree({ hierarchy, ...rest }: TreeProps) {
  return (
    <ul className="space-y-2" aria-label="Folders and chapters">
      {hierarchy.looseChapters.map((c) => (
        <ChapterRow key={c.id} chapter={c} {...rest} />
      ))}
      {hierarchy.roots.map((node) => (
        <FolderBlock key={node.folder.id} node={node} {...rest} />
      ))}
    </ul>
  );
}
