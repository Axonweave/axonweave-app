"use client";

import { useEffect, useRef } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

/**
 * Safe LaTeX rendering (spec 10.3, D-98). The expression is model output and untrusted:
 *  - KaTeX only; it never executes anything and cannot emit script or arbitrary HTML.
 *  - `trust: false` blocks \href, \url, \includegraphics, \htmlClass and friends.
 *  - `maxExpand` and `maxSize` stop macro bombs and huge glyphs.
 *  - A parse failure falls back to the plain source text (set as text, never as HTML).
 * KaTeX writes the result into the DOM itself; React's raw-HTML escape hatch is not used.
 */
export function Latex({ expression, block = true }: { expression: string; block?: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.textContent = "";
    delete el.dataset.latexError;
    try {
      katex.render(expression, el, {
        displayMode: block,
        throwOnError: true,
        trust: false,
        strict: "ignore",
        maxExpand: 200,
        maxSize: 20,
        output: "htmlAndMathml",
      });
    } catch {
      el.textContent = expression;
      el.dataset.latexError = "true";
    }
  }, [expression, block]);
  return (
    <span
      ref={ref}
      className="block max-w-full overflow-x-auto font-mono"
      role="math"
      aria-label={expression}
      data-testid="latex"
    />
  );
}
