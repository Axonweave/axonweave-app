import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { dashboardApi } from "@/lib/api/dashboard";
import { ActivityFeed } from "./activity-feed";
import type { ActivityItem } from "@/types/api";

vi.mock("@/lib/api/dashboard", () => ({ dashboardApi: { activity: vi.fn() } }));
const activity = vi.mocked(dashboardApi.activity);

const row = (n: number): ActivityItem => ({
  id: `a${n}`,
  action: "updated",
  entity_type: "subject",
  entity_id: `s${n}`,
  entity_name: `Subject ${n}`,
  workspace_id: "w1",
  created_at: "2026-11-04T10:00:00Z",
  entity_status: "active",
});

beforeEach(() => vi.resetAllMocks());

describe("ActivityFeed", () => {
  it("shows the empty state", async () => {
    activity.mockResolvedValue({ total: 0, data: [] });
    render(<ActivityFeed />);
    expect(await screen.findByText("No activity yet")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Pagination" })).not.toBeInTheDocument();
  });

  it("shows an error state", async () => {
    activity.mockRejectedValue(new Error("x"));
    render(<ActivityFeed />);
    expect(await screen.findByText("Could not load this section.")).toBeInTheDocument();
  });

  it("pages through the feed using offset", async () => {
    activity.mockImplementation(async (_limit, offset = 0) => ({
      total: 25,
      data: [row(offset + 1)],
    }));
    render(<ActivityFeed />);
    expect(await screen.findByText(/Subject 1\b/)).toBeInTheDocument();
    expect(screen.getByText("Showing 1–20 of 25")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(activity).toHaveBeenLastCalledWith(20, 20));
    expect(await screen.findByText(/Subject 21\b/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });
});
