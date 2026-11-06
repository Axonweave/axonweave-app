import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Markdown, safeUrl } from "./markdown";

function html(md: string): HTMLElement {
  const { container } = render(<Markdown content={md} />);
  return container;
}

describe("Markdown: normal content", () => {
  it("renders headings, lists, emphasis and inline code", () => {
    const c = html("## Title\n\n- one\n- two\n\n**bold** and `code`");
    expect(c.querySelector("h3")).toHaveTextContent("Title");
    expect(c.querySelectorAll("li")).toHaveLength(2);
    expect(c.querySelector("strong")).toHaveTextContent("bold");
    expect(c.querySelector("code")).toHaveTextContent("code");
  });

  it("renders GFM tables inside a scroll wrapper", () => {
    const c = html("| a | b |\n|---|---|\n| 1 | 2 |");
    expect(c.querySelector("table")).toBeInTheDocument();
    expect(c.querySelectorAll("th")).toHaveLength(2);
    expect(c.querySelector("table")?.parentElement).toHaveClass("overflow-x-auto");
  });

  it("renders fenced code with a language label and a working copy button", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    html("```python\nprint('hi')\n```");
    expect(screen.getByText("python")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /copy python block/i }));
    expect(writeText).toHaveBeenCalledWith("print('hi')");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("opens safe links in a new tab without leaking the opener", () => {
    const c = html("[docs](https://example.com/a) and [mail](mailto:a@b.co)");
    const links = c.querySelectorAll("a");
    expect(links).toHaveLength(2);
    for (const a of links) {
      expect(a).toHaveAttribute("target", "_blank");
      expect(a.getAttribute("rel")).toContain("noopener");
      expect(a.getAttribute("rel")).toContain("noreferrer");
    }
  });
});

describe("Markdown: hostile content (D-52)", () => {
  it("never creates script, iframe, style, object or embed elements from raw HTML", () => {
    const c = html(
      '<script>window.__pwned=1</script>\n\n<iframe src="https://evil"></iframe>\n\n' +
        "<style>*{display:none}</style>\n\n<object data=x></object><embed src=x>",
    );
    for (const tag of ["script", "iframe", "style", "object", "embed"]) {
      expect(c.querySelector(tag), tag).toBeNull();
    }
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });

  it("drops event-handler attributes and inline styles from raw HTML", () => {
    const c = html('<img src=x onerror="alert(1)">\n\n<p onclick="alert(1)" style="x">hi</p>');
    expect(c.innerHTML).not.toMatch(/onerror|onclick|style=/i);
  });

  it.each([
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "  javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "//evil.example/x",
  ])("neutralises the link target %s", (url) => {
    const c = html(`[click](${url})`);
    const a = c.querySelector("a");
    expect(a?.getAttribute("href") ?? "").not.toMatch(/javascript|data:|vbscript|file:|^\/\//i);
    expect(c.textContent).toContain("click");
  });

  it("does not load images (no tracking pixels), showing the alt text instead", () => {
    const c = html("![secret](https://evil.example/pixel.png?q=1)");
    expect(c.querySelector("img")).toBeNull();
    expect(c.textContent).toContain("[image: secret]");
  });

  it("keeps hostile text literal inside code blocks and inline code", () => {
    const c = html("```html\n<script>alert(1)</script>\n```\n\n`<img onerror=x>`");
    expect(c.querySelector("script")).toBeNull();
    expect(c.textContent).toContain("<script>alert(1)</script>");
    expect(c.textContent).toContain("<img onerror=x>");
  });

  it("never produces an event-handler attribute on any element", () => {
    const c = html(
      [
        '[x" onmouseover="alert(1)](https://example.com "t\\" onfocus=\\"alert(1)")',
        '<a href="https://e.co" onclick="alert(1)">raw</a>',
        '<img src=x onerror="alert(1)">',
        '<svg onload="alert(1)"><circle/></svg>',
        '<div style="background:url(javascript:alert(1))" onmouseover="x">d</div>',
      ].join("\n\n"),
    );
    for (const el of c.querySelectorAll("*")) {
      for (const attr of Array.from(el.attributes)) {
        expect(attr.name, `${el.tagName}.${attr.name}`).not.toMatch(/^on/i);
        expect(attr.name).not.toBe("style");
      }
    }
  });
});

describe("safeUrl", () => {
  it("allows http, https, mailto and same-page anchors only", () => {
    expect(safeUrl("https://a.co")).toBe("https://a.co");
    expect(safeUrl("http://a.co")).toBe("http://a.co");
    expect(safeUrl("mailto:a@b.co")).toBe("mailto:a@b.co");
    expect(safeUrl("#section")).toBe("#section");
    for (const bad of ["javascript:x", "data:x", "ftp://a", "tel:1", "/relative", "//host"]) {
      expect(safeUrl(bad), bad).toBe("");
    }
  });
});
