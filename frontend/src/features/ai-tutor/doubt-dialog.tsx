"use client";

import { useEffect, useRef, useState } from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { SendHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { Citations } from "./citations";
import { Markdown } from "./markdown";
import { QUICK_ACTIONS, type Doubt, type QuickAction } from "./use-doubts";

interface Props {
  doubt: Doubt | null;
  streaming: boolean;
  onAsk: (request: { question?: string; quick?: QuickAction }) => void;
  onClose: () => void;
}

/** Clear a doubt about selected text without touching the main conversation. */
export function DoubtDialog({ doubt, streaming, onAsk, onClose }: Props) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const lastTurn = doubt?.turns[doubt.turns.length - 1];

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [doubt?.turns.length, lastTurn?.content]);

  const close = () => {
    setText("");
    setError(null);
    onClose();
  };

  const send = () => {
    if (streaming) return;
    if (!text.trim()) {
      setError("Type a question first");
      return;
    }
    onAsk({ question: text });
    setText("");
  };

  return (
    <DialogPrimitive.Root
      open={doubt !== null}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogPortal>
        <DialogOverlay className="bg-black/50 supports-backdrop-filter:backdrop-blur-sm" />
        <DialogPrimitive.Popup
          data-testid="doubt-dialog"
          className={cn(
            "bg-popover text-popover-foreground ring-foreground/10 fixed z-50 flex flex-col gap-3 p-4 text-sm shadow-xl ring-1 outline-none",
            "inset-x-0 bottom-0 max-h-[90vh] rounded-t-2xl",
            "sm:inset-x-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:max-h-[85vh] sm:w-full sm:max-w-xl sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-xl",
          )}
        >
          <DialogTitle>Clear your doubt</DialogTitle>
          <DialogDescription className="sr-only">
            Ask a question about the text you selected. Your main chat is not changed.
          </DialogDescription>
          {doubt && (
            <>
              <blockquote className="border-primary bg-primary/10 max-h-28 overflow-y-auto rounded-md border-l-4 px-3 py-2 break-words whitespace-pre-wrap">
                {doubt.text}
              </blockquote>

              <div className="flex flex-wrap gap-2" role="group" aria-label="Quick actions">
                {QUICK_ACTIONS.map((a) => (
                  <Button
                    key={a.id}
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={streaming}
                    onClick={() => {
                      setError(null);
                      onAsk({ quick: a.id });
                    }}
                  >
                    {a.label}
                  </Button>
                ))}
              </div>

              {doubt.turns.length > 0 && (
                <div
                  className="border-border min-h-0 flex-1 space-y-3 overflow-y-auto rounded-md border p-3"
                  aria-label="Doubt thread"
                  aria-live="polite"
                >
                  {doubt.turns.map((t) =>
                    t.role === "user" ? (
                      <div key={t.id} className="flex justify-end">
                        <div className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl rounded-br-sm px-3 py-1.5 break-words whitespace-pre-wrap">
                          {t.content}
                        </div>
                      </div>
                    ) : (
                      <div key={t.id} className="min-w-0">
                        {t.content ? (
                          <div
                            className={cn(
                              t.status === "streaming" &&
                                "after:ml-0.5 after:animate-pulse after:content-['▍']",
                            )}
                          >
                            <Markdown content={t.content} />
                          </div>
                        ) : t.status === "streaming" ? (
                          <p className="text-muted-foreground">Thinking…</p>
                        ) : null}
                        {t.citations.length > 0 && <Citations citations={t.citations} />}
                      </div>
                    ),
                  )}
                  <div ref={endRef} />
                </div>
              )}
              {doubt.error && (
                <p role="alert" className="text-destructive text-sm">
                  {doubt.error}
                </p>
              )}

              <form
                className="space-y-1"
                onSubmit={(e) => {
                  e.preventDefault();
                  send();
                }}
              >
                <label htmlFor="doubt-input" className="text-muted-foreground text-xs">
                  Or type your own question
                </label>
                <div className="flex gap-2">
                  <input
                    id="doubt-input"
                    value={text}
                    maxLength={2000}
                    aria-invalid={error !== null}
                    aria-describedby={error ? "doubt-input-error" : undefined}
                    onChange={(e) => {
                      setText(e.target.value);
                      if (error) setError(null);
                    }}
                    className="border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 h-10 min-w-0 flex-1 rounded-lg border px-3 text-sm outline-none focus-visible:ring-3"
                  />
                  <Button type="submit" disabled={streaming}>
                    <SendHorizontal aria-hidden="true" />
                    Send
                  </Button>
                </div>
                {error && (
                  <p id="doubt-input-error" role="alert" className="text-destructive text-xs">
                    {error}
                  </p>
                )}
              </form>

              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <Button type="button" variant="outline" onClick={close}>
                  Back to answer
                </Button>
                <Button type="button" onClick={close}>
                  Got it
                </Button>
              </div>
            </>
          )}
        </DialogPrimitive.Popup>
      </DialogPortal>
    </DialogPrimitive.Root>
  );
}
