"use client";

import { useEffect, useRef, useState } from "react";
import { Copy, MessageCircleQuestion, Quote } from "lucide-react";
import { Button } from "@/components/ui/button";

export const MIN_SELECTION = 4;

export interface AnswerSelection {
  messageId: string;
  text: string;
  start: number;
  end: number;
}

interface Placement {
  top: number;
  left: number;
  selection: AnswerSelection;
}

/** Offset of a boundary point inside the text of `root`. */
function offsetIn(root: Element, node: Node, offset: number): number {
  const r = document.createRange();
  r.selectNodeContents(root);
  r.setEnd(node, offset);
  return r.toString().length;
}

function read(): Placement | null {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  const range = sel.getRangeAt(0);
  const from = range.startContainer.parentElement?.closest<HTMLElement>("[data-doubt-body]");
  const to = range.endContainer.parentElement?.closest<HTMLElement>("[data-doubt-body]");
  if (!from || from !== to || from.dataset.ready !== "true") return null;
  const text = sel.toString().trim();
  const messageId = from.dataset.messageId;
  if (text.length < MIN_SELECTION || !messageId) return null;
  const rect = range.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  const start = offsetIn(from, range.startContainer, range.startOffset);
  const end = offsetIn(from, range.endContainer, range.endOffset);
  const above = rect.top > 56;
  return {
    top: above ? rect.top - 44 : rect.bottom + 8,
    left: Math.min(Math.max(rect.left + rect.width / 2, 130), window.innerWidth - 130),
    selection: { messageId, text, start, end },
  };
}

interface Props {
  onCopy: (text: string) => void;
  onQuote: (text: string) => void;
  onClear: (selection: AnswerSelection) => void;
}

/** Floating actions next to selected text of a finished assistant answer. */
export function SelectionToolbar({ onCopy, onQuote, onClear }: Props) {
  const [placement, setPlacement] = useState<Placement | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let pointerDown = false;
    const later = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        if (!pointerDown) setPlacement(read());
      }, 200);
    };
    const onDown = (e: Event) => {
      if (ref.current?.contains(e.target as Node)) return;
      pointerDown = true;
      setPlacement(null);
    };
    const onUp = (e: Event) => {
      if (ref.current?.contains(e.target as Node)) return;
      pointerDown = false;
      later();
    };
    const onChange = () => {
      if (window.getSelection()?.isCollapsed) setPlacement(null);
      else later();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPlacement(null);
    };
    const hide = () => setPlacement(null);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("mouseup", onUp);
    document.addEventListener("selectionchange", onChange);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      if (timer) clearTimeout(timer);
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("mouseup", onUp);
      document.removeEventListener("selectionchange", onChange);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, []);

  if (!placement) return null;
  const { selection } = placement;
  const finish = () => {
    window.getSelection()?.removeAllRanges();
    setPlacement(null);
  };
  return (
    <div
      ref={ref}
      role="toolbar"
      aria-label="Selected text actions"
      // Keep the selection alive while a button is pressed.
      onMouseDown={(e) => e.preventDefault()}
      style={{ position: "fixed", top: placement.top, left: placement.left }}
      className="bg-popover text-popover-foreground ring-foreground/10 z-40 flex -translate-x-1/2 items-center gap-0.5 rounded-lg p-1 shadow-lg ring-1"
    >
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => {
          onCopy(selection.text);
          finish();
        }}
      >
        <Copy aria-hidden="true" />
        Copy
      </Button>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => {
          onQuote(selection.text);
          finish();
        }}
      >
        <Quote aria-hidden="true" />
        Quote in chat
      </Button>
      <Button
        type="button"
        size="sm"
        onClick={() => {
          onClear(selection);
          finish();
        }}
      >
        <MessageCircleQuestion aria-hidden="true" />
        Clear in popup
      </Button>
    </div>
  );
}
