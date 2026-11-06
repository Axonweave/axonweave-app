"use client";

import { memo, useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import "highlight.js/styles/github-dark.css";

/**
 * Model output is untrusted (rule 12, D-52). Defences, in layers:
 *  1. react-markdown never parses raw HTML (no rehype-raw): `<script>` stays literal text.
 *  2. rehype-sanitize strips anything unexpected from the tree before it is rendered.
 *  3. `urlTransform` only lets http, https and mailto through; every other scheme becomes "".
 *  4. Links always open with rel="noopener noreferrer"; images are not loaded (no tracking pixels).
 *  5. No dangerouslySetInnerHTML anywhere.
 */

const SAFE_URL = /^(https?:|mailto:)/i;

export function safeUrl(url: string): string {
  const trimmed = url.trim();
  // Same-page anchors are harmless; anything with another scheme (javascript:, data:, vbscript:) is not.
  if (trimmed.startsWith("#")) return trimmed;
  return SAFE_URL.test(trimmed) ? trimmed : "";
}

function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && "props" in node) {
    return textOf((node as { props: { children?: ReactNode } }).props.children);
  }
  return "";
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      variant="ghost"
      size="xs"
      className="text-slate-200 hover:bg-white/10 hover:text-white"
      aria-label={copied ? "Copied" : label}
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
    </Button>
  );
}

function CodeBlock({ children }: { children?: ReactNode }) {
  const code = textOf(children).replace(/\n$/, "");
  const lang = /language-([\w-]+)/.exec(
    String((children as { props?: { className?: string } } | undefined)?.props?.className ?? ""),
  )?.[1];
  return (
    <div className="border-border my-3 overflow-hidden rounded-lg border bg-[#0d1117] text-sm">
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-1">
        <span className="text-xs text-slate-300">{lang ?? "code"}</span>
        <CopyButton text={code} label={`Copy ${lang ?? "code"} block`} />
      </div>
      <pre className="overflow-x-auto p-3" tabIndex={0}>
        {children}
      </pre>
    </div>
  );
}

const components: Components = {
  a: ({ href, children }) =>
    href ? (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline underline-offset-2"
      >
        {children}
      </a>
    ) : (
      <span>{children}</span>
    ),
  img: ({ alt }) => (
    <span className="text-muted-foreground italic">[image: {alt || "omitted"}]</span>
  ),
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  code: ({ className, children }) => (
    <code
      className={
        className ? className : "bg-muted rounded px-1 py-0.5 font-mono text-[0.85em] break-words"
      }
    >
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className="my-3 max-w-full overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-border bg-muted border px-2 py-1 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border-border border px-2 py-1 align-top">{children}</td>,
  h1: ({ children }) => <h3 className="mt-4 mb-2 text-lg font-semibold">{children}</h3>,
  h2: ({ children }) => <h3 className="mt-4 mb-2 text-base font-semibold">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-3 mb-1 text-base font-semibold">{children}</h4>,
  h4: ({ children }) => <h5 className="mt-3 mb-1 text-sm font-semibold">{children}</h5>,
  p: ({ children }) => <p className="my-2 leading-relaxed break-words">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-6">{children}</ol>,
  blockquote: ({ children }) => (
    <blockquote className="border-border text-muted-foreground my-2 border-l-4 pl-3">
      {children}
    </blockquote>
  ),
};

export const Markdown = memo(function Markdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeSanitize, [rehypeHighlight, { detect: false }]]}
      urlTransform={safeUrl}
      components={components}
    >
      {content}
    </ReactMarkdown>
  );
});
