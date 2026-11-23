"use client";

/**
 * The chats of one study room, like a chat app's sidebar. A chat belongs to the room when it was
 * started on the room itself or on one of its folders or chapters.
 */
import { useCallback, useMemo, useState } from "react";
import { Archive, MessageSquare, Pencil, SquarePen, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { aiApi, type Conversation } from "@/lib/api/ai";
import { cn } from "@/lib/utils";
import { RowActions } from "@/features/academic/row-actions";
import { RenameDialog } from "@/features/ai-tutor/dialogs";
import { groupConversations } from "@/features/ai-tutor/use-conversations";
import type { LearningSpace } from "@/features/learning-spaces/space-provider";

/** The newest conversations are scanned for this room; older ones stay in the AI Tutor page. */
const SCAN = 100;

export function useRoomChats(space: LearningSpace) {
  const { subject, chapters, folders } = space;
  const ids = useMemo(() => {
    const s = new Set<string>([subject.id]);
    for (const c of chapters) s.add(c.id);
    for (const f of folders) s.add(f.id);
    return s;
  }, [subject.id, chapters, folders]);

  const list = useAsync(
    () => aiApi.listConversations({ limit: SCAN }).then((r) => r.data),
    [subject.id],
  );
  const items = useMemo(
    () =>
      (list.data ?? []).filter(
        (c) =>
          !!c.scope_id &&
          ["subject", "folder", "chapter"].includes(c.scope_type ?? "") &&
          ids.has(c.scope_id),
      ),
    [list.data, ids],
  );
  return { items, loading: list.loading && !list.data, error: list.error, reload: list.reload };
}

export function RoomChats({
  chats,
  activeId,
  onOpen,
  onNew,
  onChanged,
  chapterName,
}: {
  chats: ReturnType<typeof useRoomChats>;
  activeId: string | null;
  onOpen: (id: string | null) => void;
  onNew: () => void;
  onChanged: () => void;
  chapterName: (c: Conversation) => string | null;
}) {
  const { toast } = useToast();
  const [renaming, setRenaming] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState<Conversation | null>(null);

  const archive = useCallback(
    async (c: Conversation) => {
      try {
        await aiApi.archiveConversation(c.id);
        if (c.id === activeId) onOpen(null);
        onChanged();
        toast({ title: "Chat archived" });
      } catch {
        toast({ title: "Could not archive the chat", variant: "destructive" });
      }
    },
    [activeId, onOpen, onChanged, toast],
  );

  const remove = async () => {
    const target = deleting;
    setDeleting(null);
    if (!target) return;
    try {
      await aiApi.deleteConversation(target.id);
      if (target.id === activeId) onOpen(null);
      onChanged();
      toast({ title: "Chat deleted" });
    } catch {
      toast({ title: "Could not delete the chat", variant: "destructive" });
    }
  };

  const groups = groupConversations(chats.items);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="p-3">
        <Button variant="outline" className="w-full justify-start" onClick={onNew}>
          <SquarePen aria-hidden="true" />
          New chat
        </Button>
      </div>
      <nav aria-label="Chats in this room" className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {chats.loading ? (
          <ul className="space-y-1.5 px-1" aria-label="Loading chats">
            {[0, 1, 2].map((i) => (
              <li key={i} className="bg-muted h-8 animate-pulse rounded-lg" />
            ))}
          </ul>
        ) : chats.error ? (
          <p className="text-muted-foreground px-2 text-xs">Could not load chats.</p>
        ) : chats.items.length === 0 ? (
          <p className="text-muted-foreground px-2 py-4 text-center text-xs">
            No chats yet. Ask your first question in the box.
          </p>
        ) : (
          groups.map((g) => (
            <div key={g.label} className="mb-3">
              <p className="text-muted-foreground px-2 pb-1 text-[11px] font-medium">{g.label}</p>
              <ul className="space-y-0.5">
                {g.items.map((c) => {
                  const active = c.id === activeId;
                  const where = chapterName(c);
                  return (
                    <li key={c.id} className="group relative">
                      <button
                        type="button"
                        onClick={() => onOpen(c.id)}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                          "focus-visible:ring-ring flex w-full items-start gap-2 rounded-lg py-1.5 pr-8 pl-2 text-left text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none",
                          active
                            ? "bg-primary/10 text-foreground font-medium"
                            : "text-foreground/80 hover:bg-muted",
                        )}
                      >
                        <MessageSquare
                          className={cn(
                            "mt-0.5 h-3.5 w-3.5 shrink-0",
                            active ? "text-primary" : "text-muted-foreground",
                          )}
                          aria-hidden="true"
                        />
                        <span className="min-w-0">
                          <span className="block truncate">{c.title || "New chat"}</span>
                          {where ? (
                            <span className="text-muted-foreground block truncate text-[11px]">
                              {where}
                            </span>
                          ) : null}
                        </span>
                      </button>
                      <div className="absolute top-1 right-1 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
                        <RowActions
                          name={c.title || "this chat"}
                          actions={[
                            { label: "Rename", icon: <Pencil />, onSelect: () => setRenaming(c) },
                            {
                              label: "Archive",
                              icon: <Archive />,
                              onSelect: () => void archive(c),
                            },
                            {
                              label: "Delete",
                              icon: <Trash2 />,
                              destructive: true,
                              separated: true,
                              onSelect: () => setDeleting(c),
                            },
                          ]}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))
        )}
      </nav>

      <RenameDialog
        conversation={renaming}
        onClose={() => setRenaming(null)}
        onSaved={() => {
          setRenaming(null);
          onChanged();
          toast({ title: "Chat renamed" });
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this chat?"
        description="The chat and all of its messages will be permanently deleted. This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={() => void remove()}
      />
    </div>
  );
}
