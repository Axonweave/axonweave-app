"use client";

import { useEffect, type RefObject } from "react";
import type { Doubt } from "./use-doubts";

interface Wrapped {
  original: Text;
  middle: Text;
  after: Text | null;
  mark: HTMLElement;
}

function textNodes(root: Element): Text[] {
  const out: Text[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) out.push(n as Text);
  return out;
}

/** Where the doubted text sits now: the saved offsets if they still match, else the first match. */
function locate(full: string, doubt: Doubt): [number, number] | null {
  if (full.slice(doubt.start, doubt.end) === doubt.text.trim()) return [doubt.start, doubt.end];
  const text = doubt.text.trim();
  const at = full.indexOf(text);
  return at === -1 ? null : [at, at + text.length];
}

/** Wraps `[from, to)` of the root's text in marks, one per text node, and records how to undo it. */
function wrap(root: Element, from: number, to: number, id: string): Wrapped[] {
  const done: Wrapped[] = [];
  let pos = 0;
  for (const node of textNodes(root)) {
    const length = node.data.length;
    const a = Math.max(from - pos, 0);
    const b = Math.min(to - pos, length);
    pos += length;
    if (b <= a || a >= length) continue;
    const middle = node.splitText(a);
    const after = b - a < middle.data.length ? middle.splitText(b - a) : null;
    const mark = document.createElement("mark");
    mark.dataset.doubtId = id;
    mark.tabIndex = 0;
    mark.setAttribute("role", "button");
    mark.setAttribute("aria-label", "Reopen your doubt about this text");
    mark.className =
      "bg-primary/15 hover:bg-primary/25 cursor-pointer rounded-sm text-inherit underline decoration-dotted decoration-2 underline-offset-4";
    middle.replaceWith(mark);
    mark.append(middle);
    done.push({ original: node, middle, after, mark });
  }
  return done;
}

function unwrap(items: Wrapped[]): void {
  for (const w of [...items].reverse()) {
    if (!w.mark.isConnected) continue;
    w.original.data += w.middle.data + (w.after?.data ?? "");
    w.mark.remove();
    w.after?.remove();
  }
}

/**
 * Marks doubted text inside a rendered answer (dotted underline, soft background) and reopens the
 * popup on click or Enter. A selection that cannot be found again is simply not marked.
 */
export function useDoubtMarks(
  ref: RefObject<HTMLElement | null>,
  doubts: Doubt[],
  content: string,
  onOpen: (id: string) => void,
): void {
  useEffect(() => {
    const root = ref.current;
    if (!root || doubts.length === 0) return;
    const wrapped: Wrapped[] = [];
    try {
      const full = root.textContent ?? "";
      // Later offsets first, so wrapping one doubt does not shift the next.
      const located = doubts
        .map((d) => ({ d, at: locate(full, d) }))
        .filter((x): x is { d: Doubt; at: [number, number] } => x.at !== null)
        .sort((x, y) => y.at[0] - x.at[0]);
      let lastStart = Infinity;
      for (const { d, at } of located) {
        if (at[1] > lastStart) continue; // overlaps a later marker: skip, never fail
        lastStart = at[0];
        wrapped.push(...wrap(root, at[0], at[1], d.id));
      }
    } catch {
      /* marking is cosmetic: never break the answer */
    }
    const idOf = (e: Event) =>
      (e.target as HTMLElement | null)?.closest<HTMLElement>("mark[data-doubt-id]")?.dataset
        .doubtId ?? null;
    const click = (e: MouseEvent) => {
      const id = idOf(e);
      if (id) onOpen(id);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const id = idOf(e);
      if (id) {
        e.preventDefault();
        onOpen(id);
      }
    };
    root.addEventListener("click", click);
    root.addEventListener("keydown", key);
    return () => {
      root.removeEventListener("click", click);
      root.removeEventListener("keydown", key);
      unwrap(wrapped);
    };
  }, [ref, doubts, content, onOpen]);
}
