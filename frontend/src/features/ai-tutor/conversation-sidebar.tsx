"use client";

import Link from "next/link";
import { Archive, MessageSquarePlus, Pencil, Search, Trash2 } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/ui/loading";
import { cn } from "@/lib/utils";
import { RowActions } from "@/features/academic/row-actions";
import { useTutor } from "./tutor-context";
import { groupConversations } from "./use-conversations";

interface Props {
  activeId: string | null;
  /** Called after any navigation so the mobile drawer can close. */
  onNavigate?: () => void;
  className?: string;
}

export function ConversationSidebar({ activeId, onNavigate, className }: Props) {
  const { conversations: c, requestRename, requestDelete, archive } = useTutor();
  const groups = groupConversations(c.items);

  return (
    <nav aria-label="Conversations" className={cn("flex h-full min-h-0 flex-col", className)}>
      <div className="space-y-2 p-3">
        <Link
          href="/ai-tutor"
          onClick={onNavigate}
          className={cn(buttonVariants(), "w-full justify-start gap-2")}
        >
          <MessageSquarePlus aria-hidden="true" />
          New chat
        </Link>
        <div className="relative">
          <Search
            className="text-muted-foreground pointer-events-none absolute top-2.5 left-2.5 h-4 w-4"
            aria-hidden="true"
          />
          <Input
            type="search"
            aria-label="Search conversations"
            placeholder="Search conversations"
            value={c.query}
            onChange={(e) => c.setQuery(e.target.value)}
            maxLength={200}
            className="pl-8"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {c.loading ? (
          <div
            className="flex justify-center py-8"
            role="status"
            aria-label="Loading conversations"
          >
            <LoadingSpinner />
          </div>
        ) : c.error && c.items.length === 0 ? (
          <div className="space-y-2 p-3 text-center text-sm" role="alert">
            <p className="text-muted-foreground">Could not load conversations.</p>
            <Button variant="outline" size="sm" onClick={() => void c.reload()}>
              Try again
            </Button>
          </div>
        ) : c.items.length === 0 ? (
          <p className="text-muted-foreground p-3 text-center text-sm">
            {c.searching
              ? "No conversations match your search."
              : "No conversations yet. Start a new chat."}
          </p>
        ) : (
          <>
            {groups.map((g) => (
              <section key={g.label} aria-label={g.label} className="mb-3">
                <h2 className="text-muted-foreground px-2 py-1 text-xs font-medium">{g.label}</h2>
                <ul className="space-y-0.5">
                  {g.items.map((conv) => {
                    const title = conv.title ?? "New conversation";
                    const active = conv.id === activeId;
                    return (
                      <li
                        key={conv.id}
                        className={cn(
                          "group flex items-center rounded-lg",
                          active ? "bg-accent text-accent-foreground" : "hover:bg-accent/50",
                        )}
                      >
                        <Link
                          href={`/ai-tutor/${conv.id}`}
                          onClick={onNavigate}
                          aria-current={active ? "page" : undefined}
                          className="focus-visible:ring-ring/50 min-w-0 flex-1 truncate rounded-lg px-2 py-2 text-sm outline-none focus-visible:ring-3"
                        >
                          {title}
                        </Link>
                        <RowActions
                          name={title}
                          actions={[
                            {
                              label: "Rename",
                              icon: <Pencil />,
                              onSelect: () => requestRename(conv),
                            },
                            { label: "Archive", icon: <Archive />, onSelect: () => archive(conv) },
                            {
                              label: "Delete",
                              icon: <Trash2 />,
                              destructive: true,
                              separated: true,
                              onSelect: () => requestDelete(conv),
                            },
                          ]}
                        />
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
            {c.hasMore && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                disabled={c.loadingMore}
                onClick={() => void c.loadMore()}
              >
                {c.loadingMore ? "Loading…" : `Load more (${c.total - c.items.length} left)`}
              </Button>
            )}
          </>
        )}
      </div>
    </nav>
  );
}
