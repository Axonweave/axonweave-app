"use client";

import { useState } from "react";
import { Bot, Check, Copy, RefreshCw, ThumbsDown, ThumbsUp, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Markdown } from "./markdown";
import type { ChatError, ChatItem } from "./use-chat";

export type Rating = "positive" | "negative";

interface Props {
  item: ChatItem;
  /** The newest assistant answer: the only one that can be regenerated (the server enforces it). */
  isLatestAssistant: boolean;
  busy: boolean;
  error: ChatError | null;
  rating: Rating | null;
  onRegenerate: (messageId: string) => void;
  onRate: (messageId: string, rating: Rating) => void;
}

function CopyAction({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={() => {
        navigator.clipboard
          ?.writeText(text)
          .then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          })
          .catch(() => undefined);
      }}
    >
      {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
      {copied ? "Copied" : "Copy"}
      <span className="sr-only"> response</span>
    </Button>
  );
}

export function MessageView({
  item,
  isLatestAssistant,
  busy,
  error,
  rating,
  onRegenerate,
  onRate,
}: Props) {
  if (item.role === "user") {
    return (
      <li className="flex justify-end gap-2" data-role="user">
        <div className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl rounded-br-sm px-4 py-2 text-sm break-words whitespace-pre-wrap">
          <span className="sr-only">You said: </span>
          {item.content}
        </div>
        <span
          className="bg-muted text-muted-foreground mt-1 hidden size-7 shrink-0 items-center justify-center rounded-full sm:flex"
          aria-hidden="true"
        >
          <User className="size-4" />
        </span>
      </li>
    );
  }

  const live = item.status === "pending" || item.status === "streaming";
  const incomplete = item.status === "failed" || item.status === "cancelled";
  const canAct = item.status === "completed" && item.id !== null;

  return (
    <li className="flex gap-2" data-role="assistant" data-status={item.status}>
      <span
        className="bg-primary/10 text-primary mt-1 hidden size-7 shrink-0 items-center justify-center rounded-full sm:flex"
        aria-hidden="true"
      >
        <Bot className="size-4" />
      </span>
      <article
        className="max-w-full min-w-0 flex-1 text-sm"
        aria-label="Assistant response"
        aria-busy={live}
      >
        {item.status === "pending" ? (
          <p className="text-muted-foreground flex items-center gap-2 py-2">
            <span className="flex gap-1" aria-hidden="true">
              <span className="bg-muted-foreground size-1.5 animate-bounce rounded-full [animation-delay:-0.3s]" />
              <span className="bg-muted-foreground size-1.5 animate-bounce rounded-full [animation-delay:-0.15s]" />
              <span className="bg-muted-foreground size-1.5 animate-bounce rounded-full" />
            </span>
            Thinking…
          </p>
        ) : (
          <div
            className={cn(
              item.status === "streaming" && "after:ml-0.5 after:animate-pulse after:content-['▍']",
            )}
          >
            {item.content ? <Markdown content={item.content} /> : null}
          </div>
        )}

        {incomplete && (
          <div
            role="alert"
            className="border-border bg-muted/50 mt-2 flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2"
          >
            <span className="text-muted-foreground flex-1">
              {item.status === "cancelled"
                ? "Stopped before the answer finished."
                : (isLatestAssistant && error?.message) || "This answer did not finish."}
            </span>
            {item.id && !busy && isLatestAssistant && (
              <Button size="sm" variant="outline" onClick={() => onRegenerate(item.id!)}>
                <RefreshCw aria-hidden="true" />
                {item.status === "failed" ? "Retry" : "Regenerate"}
              </Button>
            )}
          </div>
        )}

        {canAct && (
          <div
            className="mt-1 flex flex-wrap items-center gap-1"
            role="group"
            aria-label="Response actions"
          >
            <CopyAction text={item.content} />
            {isLatestAssistant && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => onRegenerate(item.id!)}
              >
                <RefreshCw aria-hidden="true" />
                Regenerate
              </Button>
            )}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Good response"
              aria-pressed={rating === "positive"}
              className={cn(rating === "positive" && "bg-accent")}
              onClick={() => onRate(item.id!, "positive")}
            >
              <ThumbsUp aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Bad response"
              aria-pressed={rating === "negative"}
              className={cn(rating === "negative" && "bg-accent")}
              onClick={() => onRate(item.id!, "negative")}
            >
              <ThumbsDown aria-hidden="true" />
            </Button>
          </div>
        )}
      </article>
    </li>
  );
}
