"use client";

import { useEffect, useRef } from "react";
import { SendHorizontal, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  /** True while an answer is being generated: sending is blocked, Stop is offered. */
  generating: boolean;
  /** Backend input limit in characters (from /ai/status). */
  maxChars: number;
  disabled?: boolean;
}

/** Enter sends, Shift+Enter inserts a newline. Sending is blocked over the limit and while generating. */
export function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  generating,
  maxChars,
  disabled,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const wasGenerating = useRef(false);
  const over = value.length > maxChars;
  const empty = value.trim().length === 0;
  const near = value.length >= maxChars * 0.9;

  // Grow with the text, up to a cap.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  // After an answer finishes, hand focus back to the box unless the user moved on to something else.
  useEffect(() => {
    if (wasGenerating.current && !generating && document.activeElement === document.body) {
      ref.current?.focus();
    }
    wasGenerating.current = generating;
  }, [generating]);

  const submit = () => {
    if (!generating && !empty && !over && !disabled) onSend();
  };

  return (
    <form
      className="border-border bg-background border-t p-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <div className="min-w-0 flex-1">
          <label htmlFor="chat-input" className="sr-only">
            Message the AI Tutor
          </label>
          <textarea
            id="chat-input"
            ref={ref}
            rows={1}
            value={value}
            disabled={disabled}
            placeholder="Ask anything about your studies…"
            aria-describedby="chat-input-hint chat-input-count"
            aria-invalid={over}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            className={cn(
              "border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 block max-h-[200px] min-h-10 w-full resize-none rounded-lg border px-3 py-2 text-sm outline-none focus-visible:ring-3 disabled:opacity-50",
              over && "border-destructive",
            )}
          />
          <div className="text-muted-foreground mt-1 flex justify-between gap-2 text-xs">
            <span id="chat-input-hint">Enter to send, Shift+Enter for a new line</span>
            <span
              id="chat-input-count"
              className={cn(near && "text-foreground", over && "text-destructive font-medium")}
            >
              {value.length.toLocaleString()} / {maxChars.toLocaleString()}
              {over && " (too long)"}
            </span>
          </div>
        </div>
        {generating ? (
          <Button type="button" variant="outline" onClick={onStop} className="mb-6 shrink-0">
            <Square aria-hidden="true" />
            Stop
          </Button>
        ) : (
          <Button type="submit" disabled={empty || over || disabled} className="mb-6 shrink-0">
            <SendHorizontal aria-hidden="true" />
            Send
          </Button>
        )}
      </div>
    </form>
  );
}
