import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Citations, documentHref, locationLabel } from "./citations";
import { toStreamEvent, type CitationView } from "./sse";

const cite = (over: Partial<CitationView> = {}): CitationView => ({
  id: "c1",
  rank: 1,
  documentId: "d1",
  documentName: "Biology notes",
  page: 3,
  slide: null,
  heading: "Light reactions",
  snippet: "Chloroplasts convert light.",
  available: true,
  ...over,
});

describe("Citations", () => {
  it("renders nothing without sources", () => {
    const { container } = render(<Citations citations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows name and page, and the passage when opened", async () => {
    render(<Citations citations={[cite()]} />);
    expect(screen.getByText(/Biology notes · page 3/)).toBeInTheDocument();
    await userEvent.click(screen.getByText(/Biology notes/));
    expect(screen.getByText("Chloroplasts convert light.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open document" })).toHaveAttribute(
      "href",
      "/documents/d1?page=3",
    );
  });

  it("marks a deleted source and offers no link", async () => {
    render(<Citations citations={[cite({ available: false, snippet: null, documentId: null })]} />);
    expect(screen.getByText("Source deleted")).toBeInTheDocument();
    await userEvent.click(screen.getByText(/Biology notes/));
    expect(screen.getByText("The original document was deleted.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open document" })).not.toBeInTheDocument();
  });

  it("renders passage text as plain text, never as HTML", async () => {
    render(<Citations citations={[cite({ snippet: "<img src=x onerror=alert(1)>" })]} />);
    await userEvent.click(screen.getByText(/Biology notes/));
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("links to the cited page and passage", () => {
    expect(documentHref(cite({ chunkId: "abc" }))).toBe("/documents/d1?page=3&source=abc");
    expect(documentHref(cite({ page: null }))).toBe("/documents/d1");
  });

  it("labels slides", () => {
    expect(locationLabel(cite({ page: null, slide: 4 }))).toBe("slide 4");
  });
});

describe("citation stream events", () => {
  it("parses message.citations", () => {
    const ev = toStreamEvent({
      event: "message.citations",
      data: JSON.stringify({
        message_id: "m1",
        citations: [{ rank: 1, document_name: "Notes", page_number: 2, document_id: "d1" }],
      }),
    });
    expect(ev).toMatchObject({
      type: "citations",
      messageId: "m1",
      citations: [{ rank: 1, documentName: "Notes", page: 2, documentId: "d1" }],
    });
  });

  it("drops malformed citation entries", () => {
    const ev = toStreamEvent({
      event: "message.citations",
      data: JSON.stringify({ message_id: "m1", citations: [{ rank: "x" }, 5, { rank: 2 }] }),
    });
    expect(ev).toMatchObject({ type: "citations", citations: [] });
  });

  it("completed carries the validated text and citations", () => {
    const ev = toStreamEvent({
      event: "message.completed",
      data: JSON.stringify({
        message_id: "m1",
        finish_reason: "stop",
        content: "Final [1]",
        citations: [{ id: "c1", rank: 1, document_name: "Notes" }],
      }),
    });
    expect(ev).toMatchObject({ type: "completed", content: "Final [1]" });
    expect(ev?.type === "completed" && ev.citations?.[0].id).toBe("c1");
  });

  it("a plain completed event still parses", () => {
    const ev = toStreamEvent({
      event: "message.completed",
      data: JSON.stringify({ message_id: "m1", finish_reason: "stop" }),
    });
    expect(ev).toMatchObject({ type: "completed", content: null, citations: null });
  });
});
