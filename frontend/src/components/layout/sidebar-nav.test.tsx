import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppSidebar } from "./app-sidebar";
import { MobileNav } from "./mobile-nav";

let pathname = "/dashboard";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));
// The workspace switcher and room list load from the API; they have their own behaviour and are
// not part of the static navigation under test here.
vi.mock("@/features/workspaces/sidebar-workspace", () => ({ SidebarWorkspace: () => null }));

beforeEach(() => {
  pathname = "/dashboard";
});


describe("AppSidebar", () => {
  it("offers the real destinations with correct links", () => {
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    const expected: Record<string, string> = {
      Overview: "/dashboard",
      "AI Tutor": "/ai-tutor",
      Revision: "/revision",
      Progress: "/progress",
      "Knowledge Graph": "/knowledge",
      "Learner Intelligence": "/insights",
      "Research Lab": "/research",
      Settings: "/settings",
      "Help & Support": "/help",
    };
    for (const [label, href] of Object.entries(expected)) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
  });

  it("no longer lists Library, Study materials or placeholder entries", () => {
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    for (const label of ["Library", "Study materials", "Subjects", "My Workspace", "Favourites"]) {
      expect(screen.queryByRole("link", { name: label })).not.toBeInTheDocument();
    }
    expect(screen.queryByText("Coming soon")).not.toBeInTheDocument();
  });

  it("marks only the current section as active", () => {
    pathname = "/revision";
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Revision" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Progress" })).not.toHaveAttribute("aria-current");
  });

  it("highlights Research Lab, which sits under More, on the research pages", () => {
    pathname = "/research/p1";
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Research Lab" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it.each([
    "/workspaces/w1",
    "/workspaces/w1/rooms/s1",
    "/workspaces/w1/subjects/s1",
    "/workspaces/w1/subjects/s1/chapters/c1",
  ])("inside a workspace or folder (%s) the workspace list carries the highlight", (path) => {
    pathname = path;
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    for (const label of ["Overview", "AI Tutor", "Revision", "Research Lab"]) {
      expect(screen.getByRole("link", { name: label })).not.toHaveAttribute("aria-current");
    }
  });

  it("does not treat look-alike prefixes as active", () => {
    pathname = "/revision-archive";
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Revision" })).not.toHaveAttribute("aria-current");
  });

  it("collapses to icons only and the toggle announces its state", async () => {
    const onToggle = vi.fn();
    const { rerender } = render(<AppSidebar collapsed={false} onToggle={onToggle} />);
    await userEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(onToggle).toHaveBeenCalledOnce();

    rerender(<AppSidebar collapsed onToggle={onToggle} />);
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
    expect(screen.queryByText("Overview")).not.toBeInTheDocument();
    expect(screen.queryByText("Coming soon")).not.toBeInTheDocument();
  });
});

describe("AI Tutor item (D-59)", () => {
  it("is a real link, active on the chat routes, and no longer disabled", () => {
    pathname = "/ai-tutor/abc";
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    const link = screen.getByRole("link", { name: "AI Tutor" });
    expect(link).toHaveAttribute("href", "/ai-tutor");
    expect(link).not.toHaveAttribute("aria-disabled");
    expect(link).toHaveAttribute("aria-current", "page");
  });
});

describe("MobileNav drawer", () => {
  it("renders nothing while closed", () => {
    render(<MobileNav open={false} onClose={vi.fn()} />);
    expect(screen.queryByRole("link", { name: "Overview" })).not.toBeInTheDocument();
  });

  it("shows the full navigation when open", () => {
    render(<MobileNav open onClose={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AI Tutor" })).toHaveAttribute("href", "/ai-tutor");
    expect(screen.getByRole("link", { name: "Research Lab" })).toHaveAttribute("href", "/research");
  });

  it("closes with the close button, Escape and the backdrop", async () => {
    const onClose = vi.fn();
    const { container } = render(<MobileNav open onClose={onClose} />);

    await userEvent.click(screen.getByRole("button", { name: "Close menu" }));
    expect(onClose).toHaveBeenCalledTimes(1);

    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);

    const backdrop = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    await userEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("does not react to Escape while closed", async () => {
    const onClose = vi.fn();
    render(<MobileNav open={false} onClose={onClose} />);
    await userEvent.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("scopes its content to the drawer", () => {
    const { container } = render(<MobileNav open onClose={vi.fn()} />);
    const drawer = container.querySelector(".fixed") as HTMLElement;
    expect(drawer).not.toBeNull();
    expect(within(drawer).getByRole("button", { name: "Close menu" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Overview" })).toBeInTheDocument();
  });
});
