import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  formatDuration,
  formatPercent,
  ratingForKey,
  revisionApi,
  type SessionCard,
} from "@/lib/api/revision";
import { SessionRunner, remainingCards } from "./session-runner";
import { TopicTable } from "./progress-view";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock("@/lib/api/revision", async (orig) => {
  const actual = await orig<typeof import("@/lib/api/revision")>();
  return {
    ...actual,
    revisionApi: { session: vi.fn(), review: vi.fn(), completeSession: vi.fn() },
  };
});
const api = vi.mocked(revisionApi);

function card(id: string, front: string, reviewed = false): SessionCard {
  return {
    reviewed,
    card: { id, front, back: `${front} answer`, explanation: null },
    schedule: {},
  } as unknown as SessionCard;
}

describe("helpers", () => {
  it("maps keys 1-4 to ratings and ignores the rest", () => {
    expect(["1", "2", "3", "4", "5", "a"].map(ratingForKey)).toEqual([
      "again",
      "hard",
      "good",
      "easy",
      null,
      null,
    ]);
  });

  it("never turns a missing value into zero", () => {
    expect(formatPercent(null)).toBe("No data yet");
    expect(formatPercent(0)).toBe("0%");
    expect(formatPercent(72.6)).toBe("73%");
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(125)).toBe("2 min");
    expect(formatDuration(3900)).toBe("1 h 5 min");
  });

  it("keeps only unreviewed cards", () => {
    expect(remainingCards([card("a", "A", true), card("b", "B")]).map((c) => c.card.id)).toEqual([
      "b",
    ]);
  });
});

describe("topic table", () => {
  it("shows the estimate label, not a mastery claim", () => {
    render(
      <TopicTable
        rows={[
          {
            topic: "Krebs cycle",
            accuracy: 40,
            answers: 5,
            status: "needs_revision",
            status_label: "May need revision",
          } as never,
        ]}
      />,
    );
    expect(screen.getByText("Krebs cycle")).toBeInTheDocument();
    expect(screen.getByText("May need revision")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
  });
});

describe("session runner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.session.mockResolvedValue({
      id: "s1",
      status: "active",
      total_cards: 2,
      reviewed_cards: 0,
      cards: [card("c1", "Front one"), card("c2", "Front two")],
      summary: null,
    } as never);
    api.review.mockResolvedValue({} as never);
    api.completeSession.mockResolvedValue({} as never);
  });

  it("reveals the answer with space and rates with the keyboard", async () => {
    const user = userEvent.setup();
    render(<SessionRunner sessionId="s1" />);
    expect(await screen.findByText("Front one")).toBeInTheDocument();
    expect(screen.queryByText("Front one answer")).not.toBeInTheDocument();

    await user.keyboard(" ");
    expect(screen.getByText("Front one answer")).toBeInTheDocument();
    await user.keyboard("3");

    await waitFor(() => expect(api.review).toHaveBeenCalledTimes(1));
    const [cardId, body] = api.review.mock.calls[0];
    expect(cardId).toBe("c1");
    expect(body).toMatchObject({ rating: "good", session_id: "s1" });
    expect(body.idempotency_key).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(await screen.findByText("Front two")).toBeInTheDocument();
  });

  it("does not rate before the answer is shown", async () => {
    const user = userEvent.setup();
    render(<SessionRunner sessionId="s1" />);
    await screen.findByText("Front one");
    await user.keyboard("3");
    expect(api.review).not.toHaveBeenCalled();
  });

  it("completes the session after the last card", async () => {
    api.session.mockResolvedValue({
      id: "s1",
      status: "active",
      total_cards: 1,
      reviewed_cards: 0,
      cards: [card("c1", "Only card")],
      summary: null,
    } as never);
    const user = userEvent.setup();
    render(<SessionRunner sessionId="s1" />);
    await screen.findByText("Only card");
    await user.keyboard(" ");
    await user.keyboard("4");
    expect(await screen.findByTestId("session-complete")).toBeInTheDocument();
    await waitFor(() => expect(api.completeSession).toHaveBeenCalledWith("s1"));
  });
});
