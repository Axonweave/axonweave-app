import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { dashboardApi } from "@/lib/api/dashboard";
import { RecentActivity } from "./recent-activity";
import { RecentSubjects } from "./recent-subjects";
import { StatsStrip } from "./stats-strip";
import { WorkspaceOverview } from "./workspace-overview";
import { QuickActions } from "./quick-actions";
import { WelcomeHeader } from "./welcome-header";
import type { ActivityItem } from "@/types/api";

vi.mock("@/lib/api/dashboard", () => ({
  dashboardApi: {
    stats: vi.fn(),
    workspaces: vi.fn(),
    recentSubjects: vi.fn(),
    activity: vi.fn(),
    archived: vi.fn(),
  },
}));

const authState = vi.hoisted(() => ({
  value: { user: null, loading: false, refresh: async () => {} } as {
    user: unknown;
    loading: boolean;
    refresh: () => Promise<void>;
  },
}));
vi.mock("@/contexts/auth-context", () => ({ useAuthContext: () => authState.value }));

const api = vi.mocked(dashboardApi);

const activity = (over: Partial<ActivityItem> = {}): ActivityItem => ({
  id: "a1",
  action: "created",
  entity_type: "workspace",
  entity_id: "w1",
  entity_name: "Uni",
  workspace_id: "w1",
  created_at: "2026-11-04T10:00:00Z",
  entity_status: "active",
  ...over,
});

beforeEach(() => vi.resetAllMocks());

describe("WelcomeHeader", () => {
  it("greets the logged-in user by name", () => {
    authState.value = {
      user: { email: "a@b.c", profile: { full_name: "Ada Lovelace" } },
      loading: false,
      refresh: async () => {},
    };
    render(<WelcomeHeader />);
    expect(screen.getByRole("heading", { name: "Welcome back, Ada Lovelace" })).toBeInTheDocument();
  });

  it("shows a loading placeholder, not a made-up name, while the user loads", () => {
    authState.value = { user: null, loading: true, refresh: async () => {} };
    render(<WelcomeHeader />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });
});

describe("QuickActions", () => {
  it("opens the create-workspace flow and offers no dead subject/folder/chapter buttons", async () => {
    const onCreate = vi.fn();
    render(<QuickActions onCreateWorkspace={onCreate} />);
    await userEvent.click(screen.getByRole("button", { name: /create workspace/i }));
    expect(onCreate).toHaveBeenCalledOnce();
    expect(
      screen.queryByRole("button", { name: /subject|folder|chapter/i }),
    ).not.toBeInTheDocument();
  });
});

describe("StatsStrip", () => {
  it("renders real counts, including zero", async () => {
    api.stats.mockResolvedValue({
      workspace_count: 2,
      subject_count: 0,
      folder_count: 0,
      chapter_count: 0,
      chapter_status: { not_started: 0, in_progress: 0, completed: 0 },
    });
    render(<StatsStrip />);
    expect(await screen.findByText("Workspaces")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows loading then an error with retry", async () => {
    api.stats.mockRejectedValueOnce(new Error("x")).mockResolvedValueOnce({
      workspace_count: 1,
      subject_count: 1,
      folder_count: 1,
      chapter_count: 1,
      chapter_status: { not_started: 1, in_progress: 0, completed: 0 },
    });
    render(<StatsStrip />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Folders")).toBeInTheDocument();
  });
});

describe("WorkspaceOverview", () => {
  it("shows workspace cards from the API", async () => {
    api.workspaces.mockResolvedValue({
      total: 1,
      data: [
        {
          id: "w1",
          name: "Uni",
          description: "My degree",
          is_default: false,
          subject_count: 3,
          updated_at: "2026-11-04T10:00:00Z",
        },
      ],
    });
    render(<WorkspaceOverview onCreateWorkspace={vi.fn()} />);
    expect(await screen.findByText("Uni")).toBeInTheDocument();
    expect(screen.getByText("My degree")).toBeInTheDocument();
    expect(screen.getByText("3 subjects")).toBeInTheDocument();
  });

  it("shows an empty state whose button creates a workspace", async () => {
    api.workspaces.mockResolvedValue({ total: 0, data: [] });
    const onCreate = vi.fn();
    render(<WorkspaceOverview onCreateWorkspace={onCreate} />);
    await userEvent.click(await screen.findByRole("button", { name: "Create workspace" }));
    expect(onCreate).toHaveBeenCalledOnce();
  });

  it("shows an error state", async () => {
    api.workspaces.mockRejectedValue(new Error("x"));
    render(<WorkspaceOverview onCreateWorkspace={vi.fn()} />);
    expect(await screen.findByText("Could not load this section.")).toBeInTheDocument();
  });
});

describe("RecentSubjects", () => {
  it("lists subjects with their workspace", async () => {
    api.recentSubjects.mockResolvedValue([
      {
        id: "s1",
        name: "Maths",
        workspace_id: "w1",
        workspace_name: "Uni",
        updated_at: "2026-11-04T10:00:00Z",
      },
    ]);
    render(<RecentSubjects />);
    expect(await screen.findByText("Maths")).toBeInTheDocument();
    expect(screen.getByText(/Uni · Updated/)).toBeInTheDocument();
  });

  it("shows empty and error states", async () => {
    api.recentSubjects.mockResolvedValueOnce([]);
    const { unmount } = render(<RecentSubjects />);
    expect(await screen.findByText("No subjects yet")).toBeInTheDocument();
    unmount();
    api.recentSubjects.mockRejectedValueOnce(new Error("x"));
    render(<RecentSubjects />);
    expect(await screen.findByText("Could not load this section.")).toBeInTheDocument();
  });
});

describe("RecentActivity", () => {
  it("renders sentences and links only entities that still exist", async () => {
    api.activity.mockResolvedValue({
      total: 2,
      data: [activity(), activity({ id: "a2", entity_name: "Old", entity_status: "deleted" })],
    });
    render(<RecentActivity />);
    const live = await screen.findByRole("link", { name: /Created workspace .Uni./ });
    expect(live).toHaveAttribute("href", "/workspaces");
    expect(screen.getByText(/Created workspace .Old./)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Old/ })).not.toBeInTheDocument();
  });

  it("shows empty and error states", async () => {
    api.activity.mockResolvedValueOnce({ total: 0, data: [] });
    const { unmount } = render(<RecentActivity />);
    expect(await screen.findByText("No activity yet")).toBeInTheDocument();
    unmount();
    api.activity.mockRejectedValueOnce(new Error("x"));
    render(<RecentActivity />);
    expect(await screen.findByText("Could not load this section.")).toBeInTheDocument();
  });
});
