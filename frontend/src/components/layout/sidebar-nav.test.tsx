import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppSidebar } from "./app-sidebar";
import { MobileNav } from "./mobile-nav";

let pathname = "/dashboard";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

beforeEach(() => {
  pathname = "/dashboard";
});

const COMING_SOON = [
  "AI Tutor",
  "Research Studio",
  "Assessments",
  "Revision",
  "Library",
  "Favourites",
];

describe("AppSidebar", () => {
  it("offers the real Phase 1 destinations with correct links", () => {
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    const expected: Record<string, string> = {
      Overview: "/dashboard",
      "My Workspace": "/workspaces",
      Subjects: "/subjects",
      "Recent Activity": "/activity",
      "Archived Items": "/archived",
      Settings: "/settings",
      "Help & Support": "/help",
    };
    for (const [label, href] of Object.entries(expected)) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
  });

  it.each(COMING_SOON)("%s is disabled and cannot be focused or followed", (label) => {
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    const link = screen.getByRole("link", { name: new RegExp(`^${label}`) });
    expect(link).toHaveAttribute("aria-disabled", "true");
    expect(link).toHaveAttribute("href", "#");
    expect(link).toHaveAttribute("tabindex", "-1");
    expect(link.className).toContain("pointer-events-none");
    expect(link).toHaveTextContent("(soon)");
  });

  it("labels the group as coming soon", () => {
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
  });

  it("marks only the current section as active", () => {
    pathname = "/archived";
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Archived Items" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
    for (const label of COMING_SOON) {
      expect(screen.getByRole("link", { name: new RegExp(`^${label}`) })).not.toHaveAttribute(
        "aria-current",
      );
    }
  });

  it.each([
    ["/subjects", "Subjects", "My Workspace"],
    ["/workspaces/w1/subjects/s1", "Subjects", "My Workspace"],
    ["/workspaces/w1/subjects/s1/chapters/c1", "Subjects", "My Workspace"],
    ["/workspaces", "My Workspace", "Subjects"],
  ])("on %s highlights %s and not %s", (path, on, off) => {
    pathname = path;
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    expect(screen.getByRole("link", { name: on })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: off })).not.toHaveAttribute("aria-current");
  });

  it("does not treat look-alike prefixes as active", () => {
    pathname = "/subjects-archive";
    render(<AppSidebar collapsed={false} onToggle={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Subjects" })).not.toHaveAttribute("aria-current");
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

describe("MobileNav drawer", () => {
  it("renders nothing while closed", () => {
    render(<MobileNav open={false} onClose={vi.fn()} />);
    expect(screen.queryByRole("link", { name: "Overview" })).not.toBeInTheDocument();
  });

  it("shows the full navigation when open, including disabled future modules", () => {
    render(<MobileNav open onClose={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    const soon = screen.getByRole("link", { name: /^AI Tutor/ });
    expect(soon).toHaveAttribute("aria-disabled", "true");
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
