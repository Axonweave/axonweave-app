"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingSpinner } from "@/components/ui/loading";
import { aiApi, type AiStatus, type Conversation, type UsageSummary } from "@/lib/api/ai";
import { ApiRequestError } from "@/lib/api/client";

// ── rename ───────────────────────────────────────────────────────────────────

function RenameForm({
  conversation,
  onClose,
  onSaved,
}: {
  conversation: Conversation;
  onClose: () => void;
  onSaved: (c: Conversation) => void;
}) {
  const [title, setTitle] = useState(conversation.title ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next = title.trim();
    if (!next) return setError("Enter a title.");
    setBusy(true);
    setError(null);
    try {
      onSaved(await aiApi.renameConversation(conversation.id, next));
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Could not rename the conversation.");
      setBusy(false);
    }
  };

  return (
    <DialogContent showCloseButton={false}>
      <form onSubmit={submit} className="space-y-4">
        <DialogHeader>
          <DialogTitle>Rename conversation</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="conversation-title">Title</Label>
          <Input
            id="conversation-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            autoFocus
            required
          />
        </div>
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

export function RenameDialog({
  conversation,
  onClose,
  onSaved,
}: {
  conversation: Conversation | null;
  onClose: () => void;
  onSaved: (c: Conversation) => void;
}) {
  return (
    <Dialog open={conversation !== null} onOpenChange={(open) => !open && onClose()}>
      {conversation && (
        <RenameForm
          key={conversation.id}
          conversation={conversation}
          onClose={onClose}
          onSaved={onSaved}
        />
      )}
    </Dialog>
  );
}

// ── privacy notice (D-54) ────────────────────────────────────────────────────

/** The provider name comes from the server's configuration, never from this component. */
export function noticeText(status: AiStatus): string {
  if (status.is_test_provider) {
    return `This server is using a test provider (${status.provider_display_name ?? "test"}). It is not a real AI: replies are generated locally for testing and nothing is sent to an outside service.`;
  }
  const name = status.provider_display_name ?? "the configured AI provider";
  return `To answer you, the text of your messages and the earlier messages in the conversation are sent to ${name}, an external service. Do not share passwords or other secrets. If you ask about your documents, the matching passages are sent too, and the text of documents you upload is sent to an embedding service so it can be searched. Your conversations and documents are stored in your Axonweave account and only you can see them.`;
}

export function NoticeDialog({
  open,
  status,
  onAcknowledged,
}: {
  open: boolean;
  status: AiStatus;
  onAcknowledged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const accept = async () => {
    setBusy(true);
    setError(null);
    try {
      await aiApi.acknowledgeNotice();
      onAcknowledged();
    } catch {
      setError("Could not save your acknowledgement. Please try again.");
      setBusy(false);
    }
  };

  // Not dismissable: the AI Tutor stays locked until the notice is acknowledged (or the user leaves).
  return (
    <Dialog open={open} onOpenChange={() => undefined} disablePointerDismissal>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Before you start</DialogTitle>
          <DialogDescription>How the AI Tutor handles your messages</DialogDescription>
        </DialogHeader>
        <p className="text-sm leading-relaxed">{noticeText(status)}</p>
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}
        <DialogFooter>
          <Link href="/dashboard" className={buttonVariants({ variant: "outline" })}>
            Not now
          </Link>
          <Button onClick={() => void accept()} disabled={busy}>
            {busy ? "Saving…" : "I understand"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── usage ────────────────────────────────────────────────────────────────────

function formatCost(u: UsageSummary): string {
  if (u.requests === 0) return "None yet";
  if (u.cost_by_currency.length === 0 || u.cost_known_requests === 0) return "Unknown";
  const amounts = u.cost_by_currency
    .map((c) => `${c.currency} ${Number(c.amount).toFixed(4)}`)
    .join(" + ");
  return u.cost_known_requests < u.requests
    ? `${amounts} for ${u.cost_known_requests} of ${u.requests} requests (the rest unknown)`
    : amounts;
}

function formatTokens(u: UsageSummary): string {
  if (u.requests === 0) return "None yet";
  if (u.token_known_requests === 0) return "Unknown";
  const total = `${u.total_tokens.toLocaleString()} (${u.input_tokens.toLocaleString()} in, ${u.output_tokens.toLocaleString()} out)`;
  return u.token_known_requests < u.requests
    ? `${total} from ${u.token_known_requests} of ${u.requests} requests`
    : total;
}

export function UsageDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [data, setData] = useState<UsageSummary | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    let live = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setData(null);
    setFailed(false);
    aiApi
      .usageSummary(30)
      .then((d) => live && setData(d))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [open]);

  const rows: [string, string][] = data
    ? [
        ["Requests", String(data.requests)],
        ["Failed", String(data.failed_requests)],
        ["Stopped", String(data.cancelled_requests)],
        ["Tokens", formatTokens(data)],
        ["Estimated cost", formatCost(data)],
      ]
    : [];

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>AI usage, last 30 days</DialogTitle>
          <DialogDescription>
            Your own usage only. Cost is an estimate, shown only where the price is known.
          </DialogDescription>
        </DialogHeader>
        {failed ? (
          <p role="alert" className="text-destructive text-sm">
            Could not load usage.
          </p>
        ) : !data ? (
          <div className="flex justify-center py-6">
            <LoadingSpinner />
          </div>
        ) : (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            {rows.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted-foreground">{k}</dt>
                <dd className="text-right font-medium break-words">{v}</dd>
              </div>
            ))}
          </dl>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
