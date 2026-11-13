import Link from "next/link";
import { evidenceHref, type KnowledgeEvidence } from "@/lib/api/knowledge";

/** Only an absolute https link is ever rendered as a link; anything else is shown as plain text. */
export function safeWebUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

/**
 * Where a piece of evidence came from: a link to the document passage, or, for a concept built from
 * a web search, a "Web" badge and the website's title as an external link. Text only: the page is
 * never embedded, and the link opens in a new tab with no referrer or opener.
 */
export function EvidenceSource({ ev, className }: { ev: KnowledgeEvidence; className?: string }) {
  if (ev.source_kind === "web") {
    const href = safeWebUrl(ev.source_url);
    const title = ev.source_title || ev.source_url || "Website";
    return (
      <span className="inline-flex flex-wrap items-center gap-1.5">
        <span className="bg-muted text-muted-foreground rounded-full px-1.5 py-0.5 text-[10px] font-medium">
          Web
        </span>
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className={className ?? "text-primary hover:underline"}
          >
            {title}
          </a>
        ) : (
          <span>{title}</span>
        )}
      </span>
    );
  }
  if (!ev.document_id) return <span>{ev.document_name ?? "Source"}</span>;
  return (
    <Link href={evidenceHref(ev)} className={className ?? "text-primary hover:underline"}>
      {ev.document_name}
    </Link>
  );
}
