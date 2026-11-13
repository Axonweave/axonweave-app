import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { KnowledgeEvidence } from "@/lib/api/knowledge";
import { EvidenceSource, safeWebUrl } from "./evidence-source";

function ev(over: Partial<KnowledgeEvidence>): KnowledgeEvidence {
  return {
    source_kind: "document",
    document_id: "d1",
    document_name: "Notes.pdf",
    chunk_id: null,
    page_number: 3,
    slide_number: null,
    ...over,
  } as KnowledgeEvidence;
}

describe("EvidenceSource", () => {
  it("links document evidence to the document viewer", () => {
    render(<EvidenceSource ev={ev({})} />);
    expect(screen.getByRole("link", { name: "Notes.pdf" })).toHaveAttribute(
      "href",
      "/documents/d1?page=3",
    );
    expect(screen.queryByText("Web")).not.toBeInTheDocument();
  });

  it("shows web evidence with a Web badge and a safe external link", () => {
    render(
      <EvidenceSource
        ev={ev({
          source_kind: "web",
          document_id: null,
          document_name: null,
          source_url: "https://example.org/cells",
          source_title: "Cell biology primer",
        })}
      />,
    );
    expect(screen.getByText("Web")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Cell biology primer" });
    expect(link).toHaveAttribute("href", "https://example.org/cells");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });

  it("never renders a non-https address as a link", () => {
    render(
      <EvidenceSource
        ev={ev({
          source_kind: "web",
          document_id: null,
          source_url: "javascript:alert(1)",
          source_title: "Bad",
        })}
      />,
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("Bad")).toBeInTheDocument();
  });

  it("accepts only https URLs", () => {
    expect(safeWebUrl("https://a.org/x")).toBe("https://a.org/x");
    expect(safeWebUrl("http://a.org")).toBeNull();
    expect(safeWebUrl("data:text/html,x")).toBeNull();
    expect(safeWebUrl("not a url")).toBeNull();
    expect(safeWebUrl(null)).toBeNull();
  });
});
