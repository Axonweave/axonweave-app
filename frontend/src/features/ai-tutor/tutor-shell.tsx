"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorDisplay } from "@/components/ui/error-display";
import { LoadingPage } from "@/components/ui/loading";
import { useToast } from "@/hooks/use-toast";
import { aiApi, type AiModel, type AiStatus, type Conversation } from "@/lib/api/ai";
import { ApiRequestError } from "@/lib/api/client";
import { ChatPanel } from "./chat-panel";
import { ConversationSidebar } from "./conversation-sidebar";
import { NoticeDialog, RenameDialog, UsageDialog } from "./dialogs";
import { TutorProvider } from "./tutor-context";
import { useConversations } from "./use-conversations";

type Boot =
  | { state: "loading" }
  | { state: "error" }
  | { state: "ready"; status: AiStatus; models: AiModel[]; acknowledged: boolean };

/** `/ai-tutor` -> null (new chat), `/ai-tutor/<id>` -> id. */
export function conversationIdFromPath(pathname: string): string | null {
  const match = /^\/ai-tutor\/([^/]+)\/?$/.exec(pathname);
  return match ? decodeURIComponent(match[1]) : null;
}

function Drawer({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    panel.current?.querySelector<HTMLElement>("button, a, input")?.focus();
    return () => {
      (opener.current as HTMLElement | null)?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") return onClose();
    if (e.key !== "Tab") return;
    const focusable = panel.current?.querySelectorAll<HTMLElement>(
      "a[href], button:not([disabled]), input:not([disabled])",
    );
    if (!focusable?.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="fixed inset-0 z-40 md:hidden" onKeyDown={onKeyDown}>
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden="true" />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label="Conversations"
        className="bg-background absolute inset-y-0 left-0 flex w-[85%] max-w-xs flex-col shadow-xl"
      >
        <div className="border-border flex items-center justify-between border-b px-3 py-2">
          <span className="text-sm font-semibold">Conversations</span>
          <Button variant="ghost" size="icon" aria-label="Close conversations" onClick={onClose}>
            <X aria-hidden="true" />
          </Button>
        </div>
        <div className="min-h-0 flex-1">{children}</div>
      </div>
    </div>
  );
}

/** Loads status and preferences first; the conversation list is only fetched once AI is usable. */
export function TutorShell() {
  const [boot, setBoot] = useState<Boot>({ state: "loading" });

  const start = useCallback(async () => {
    setBoot({ state: "loading" });
    try {
      const [status, prefs] = await Promise.all([aiApi.status(), aiApi.preferences()]);
      // Not configured: no model call is possible, so do not ask for models (they would 503).
      const models = status.configured ? await aiApi.models() : [];
      setBoot({
        state: "ready",
        status,
        models,
        acknowledged: prefs.ai_notice_acknowledged_at !== null,
      });
    } catch {
      setBoot({ state: "error" });
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void start();
  }, [start]);

  if (boot.state === "loading") return <LoadingPage />;
  if (boot.state === "error")
    return (
      <ErrorDisplay
        title="Could not open the AI Tutor"
        message="Check your connection and try again."
        onRetry={() => void start()}
      />
    );

  if (!boot.status.configured) {
    return (
      <div className="p-6" data-testid="ai-not-configured">
        <EmptyState
          title="AI is not configured"
          description="The AI Tutor needs an AI provider, and none has been set up on this server yet. Ask whoever runs Axonweave to configure one. The rest of the app works as usual."
          action={
            <Link href="/dashboard" className={buttonVariants()}>
              Back to dashboard
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <TutorWorkspace
      status={boot.status}
      models={boot.models}
      acknowledged={boot.acknowledged}
      onAcknowledged={() => setBoot({ ...boot, acknowledged: true })}
    />
  );
}

function TutorWorkspace({
  status,
  models,
  acknowledged,
  onAcknowledged,
}: {
  status: AiStatus;
  models: AiModel[];
  acknowledged: boolean;
  onAcknowledged: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { toast } = useToast();
  const conversationId = conversationIdFromPath(pathname);

  const [modelId, setModelId] = useState<string | null>(null);
  const conversations = useConversations();

  const [renaming, setRenaming] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState<Conversation | null>(null);
  const [usageOpen, setUsageOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const archive = useCallback(
    async (c: Conversation) => {
      try {
        await aiApi.archiveConversation(c.id);
        conversations.remove(c.id);
        if (c.id === conversationId) router.replace("/ai-tutor");
        toast({ title: "Conversation archived" });
      } catch (e) {
        toast({
          title: "Could not archive",
          description: e instanceof ApiRequestError ? e.message : undefined,
          variant: "destructive",
        });
      }
    },
    [conversationId, conversations, router, toast],
  );

  const confirmDelete = async () => {
    const target = deleting;
    setDeleting(null);
    if (!target) return;
    try {
      await aiApi.deleteConversation(target.id);
      conversations.remove(target.id);
      if (target.id === conversationId) router.replace("/ai-tutor");
      toast({ title: "Conversation deleted" });
    } catch (e) {
      toast({
        title: "Could not delete",
        description: e instanceof ApiRequestError ? e.message : undefined,
        variant: "destructive",
      });
    }
  };

  const value = useMemo(
    () => ({
      status,
      models,
      modelId,
      setModelId,
      conversations,
      requestRename: setRenaming,
      requestDelete: setDeleting,
      archive: (c: Conversation) => void archive(c),
      openUsage: () => setUsageOpen(true),
      openDrawer: () => setDrawerOpen(true),
    }),
    [status, models, modelId, conversations, archive],
  );

  return (
    <TutorProvider value={value}>
      <div className="flex h-full min-h-0 w-full">
        <aside className="border-border hidden w-72 shrink-0 border-r md:block">
          <ConversationSidebar activeId={conversationId} />
        </aside>
        <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
          <ConversationSidebar activeId={conversationId} onNavigate={() => setDrawerOpen(false)} />
        </Drawer>
        <ChatPanel conversationId={conversationId} />
      </div>

      <RenameDialog
        conversation={renaming}
        onClose={() => setRenaming(null)}
        onSaved={(c) => {
          conversations.replace(c);
          setRenaming(null);
          toast({ title: "Conversation renamed" });
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this conversation?"
        description="The conversation and all of its messages will be permanently deleted. This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={() => void confirmDelete()}
      />
      <UsageDialog open={usageOpen} onClose={() => setUsageOpen(false)} />
      <NoticeDialog open={!acknowledged} status={status} onAcknowledged={onAcknowledged} />
    </TutorProvider>
  );
}
