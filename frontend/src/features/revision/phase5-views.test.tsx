import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { analyticsApi } from "@/lib/api/revision";
import { RevisionWidget } from "@/features/dashboard/revision-widget";
import { CompareTable, formatChange } from "@/features/study/attempt-compare";
import { canCompare } from "@/features/study/quiz-history";
import type { QuizCompare, QuizHistoryItem } from "@/lib/api/study";
import { buildWeeks, shade } from "./calendar-grid";
import { barFractions, trendCoordinates } from "./charts";
import { SubjectTable } from "./progress-view";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@/lib/api/revision", async (orig) => {
  const actual = await orig<typeof import("@/lib/api/revision")>();
  return { ...actual, analyticsApi: { overview: vi.fn() } };
});
const api = vi.mocked(analyticsApi);

beforeEach(() => vi.resetAllMocks());

describe("buildWeeks", () => {
  it("pads to Monday-first weeks and fills days the backend did not return", () => {
    // 2026-11-04 is a Wednesday, 2026-11-10 a Tuesday
    const weeks = buildWeeks(
      [{ date: "2026-11-05", activities: 2, quiz_attempts: 1, reviews: 1 }],
      "2026-11-04",
      "2026-11-10",
    );
    expect(weeks).toHaveLength(2);
    expect(weeks[0].slice(0, 2)).toEqual([null, null]);
    expect(weeks[0][2]?.date).toBe("2026-11-04");
    expect(weeks[0][3]?.activities).toBe(2);
    expect(weeks[0][2]?.activities).toBe(0);
    expect(weeks[1].filter(Boolean)).toHaveLength(2);
    expect(weeks.every((w) => w.length === 7)).toBe(true);
  });

  it("returns nothing for an invalid or reversed range", () => {
    expect(buildWeeks([], "2026-11-10", "2026-11-01")).toEqual([]);
    expect(buildWeeks([], "bad", "2026-11-01")).toEqual([]);
  });

  it("shades empty days neutral and busy days darker", () => {
    expect(shade(0, 10)).toBe("bg-muted");
    expect(shade(5, 0)).toBe("bg-muted");
    expect(shade(10, 10)).not.toBe(shade(1, 10));
  });
});

describe("chart maths", () => {
  it("skips missing values instead of plotting them as zero", () => {
    const coords = trendCoordinates([
      { label: "a", value: 50 },
      { label: "b", value: null },
      { label: "c", value: 100 },
    ]);
    expect(coords.map((c) => c.label)).toEqual(["a", "c"]);
    expect(coords[1].y).toBeLessThan(coords[0].y); // higher score sits higher on screen
  });

  it("scales bars to the largest value and handles all zeros", () => {
    expect(
      barFractions([
        { label: "a", value: 2 },
        { label: "b", value: 4 },
      ]),
    ).toEqual([0.5, 1]);
    expect(barFractions([{ label: "a", value: 0 }])).toEqual([0]);
  });
});

describe("SubjectTable", () => {
  it("shows a subject row without inventing numbers for missing data", () => {
    render(
      <SubjectTable
        rows={[
          {
            subject_id: "s1",
            subject_name: "Biology",
            quiz_attempts: 0,
            average_quiz_percentage: null,
            last_attempt_at: null,
            reviews: 0,
            hard_or_again_share: null,
          },
        ]}
      />,
    );
    expect(screen.getByText("Biology")).toBeInTheDocument();
    expect(screen.getAllByText("No data yet")).toHaveLength(2);
  });
});

const item = (over: Partial<QuizHistoryItem>): QuizHistoryItem =>
  ({
    id: "a1",
    quiz_id: "q1",
    status: "submitted",
    started_at: "2026-11-01T10:00:00Z",
    ...over,
  }) as QuizHistoryItem;

describe("quiz history helpers", () => {
  it("only allows comparing two different submitted attempts of the same quiz", () => {
    expect(canCompare(item({ id: "a" }), item({ id: "b" }))).toBe(true);
    expect(canCompare(item({ id: "a" }), item({ id: "a" }))).toBe(false);
    expect(canCompare(item({ id: "a" }), item({ id: "b", quiz_id: "q2" }))).toBe(false);
    expect(canCompare(item({ id: "a" }), item({ id: "b", status: "in_progress" }))).toBe(false);
    expect(canCompare(item({ id: "a" }), undefined)).toBe(false);
  });

  it("formats signed changes and missing values", () => {
    expect(formatChange(5)).toBe("+5");
    expect(formatChange(-3, " pts")).toBe("-3 pts");
    expect(formatChange(0)).toBe("0");
    expect(formatChange(null)).toBe("–");
  });
});

describe("CompareTable", () => {
  it("shows movement per question and the backend note", () => {
    const data = {
      first: { percentage: 50 },
      second: { percentage: 100 },
      score_change: 1,
      percentage_change: 50,
      time_change_seconds: -30,
      topics: [{ topic: "Cells", first_percentage: 50, second_percentage: 100, change: 50 }],
      questions: [
        {
          question_id: "x",
          question: "What is a cell?",
          topic: "Cells",
          first: "incorrect",
          second: "correct",
          movement: "improved",
        },
      ],
      note: "Comparison note.",
    } as unknown as QuizCompare;
    render(<CompareTable data={data} />);
    expect(screen.getByText("What is a cell?")).toBeInTheDocument();
    expect(screen.getByText("Improved")).toBeInTheDocument();
    expect(screen.getByText("Comparison note.")).toBeInTheDocument();
    // once in the summary tile, once in the topic row
    expect(screen.getAllByText("+50 pts")).toHaveLength(2);
  });
});

describe("RevisionWidget", () => {
  it("shows the real due, overdue and streak figures with a link to revision", async () => {
    api.overview.mockResolvedValue({
      due_today: 4,
      overdue: 2,
      current_streak_days: 3,
      topics_needing_attention: 1,
    } as never);
    render(<RevisionWidget />);
    await waitFor(() => expect(screen.getByText("Due today")).toBeInTheDocument());
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("3 days")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open revision" })).toHaveAttribute(
      "href",
      "/revision",
    );
  });

  it("says nothing is due instead of showing a fake call to action", async () => {
    api.overview.mockResolvedValue({
      due_today: 0,
      overdue: 0,
      current_streak_days: 0,
      topics_needing_attention: 0,
    } as never);
    render(<RevisionWidget />);
    await waitFor(() => expect(screen.getByText(/Nothing is due right now/)).toBeInTheDocument());
  });

  it("shows an error with retry when the request fails", async () => {
    api.overview.mockRejectedValue(new Error("boom"));
    render(<RevisionWidget />);
    await waitFor(() => expect(screen.getByText("Could not load")).toBeInTheDocument());
  });
});
