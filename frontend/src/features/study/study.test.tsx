import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/lib/api/client";
import { studyApi, type Flashcard, type QuizAttempt, type StudyMaterial } from "@/lib/api/study";
import { EXPORT_FORMATS } from "./export-menu";
import { StudyMode, shuffled } from "./flashcards-view";
import { buildSettings, GENERATORS } from "./generate-dialog";
import { Latex } from "./latex";
import { FormulaView } from "./material-views";
import { PayloadEditor } from "./payload-editor";
import { QuizTaker, formatClock, isAnswered } from "./quiz-taker";
import { SourceRefs } from "./sources";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
const push = vi.fn();
const router = { push, replace: push };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock("@/lib/api/study", async (orig) => {
  const actual = await orig<typeof import("@/lib/api/study")>();
  return {
    ...actual,
    studyApi: {
      get: vi.fn(),
      startAttempt: vi.fn(),
      saveAnswers: vi.fn(),
      submit: vi.fn(),
    },
  };
});
const api = vi.mocked(studyApi);

describe("generation settings", () => {
  it("sends only the settings the user touched, clamped to the allowed range", () => {
    const flash = GENERATORS.find((g) => g.type === "flashcards")!;
    expect(buildSettings(flash.fields, {}, "")).toEqual({});
    expect(buildSettings(flash.fields, { count: "500", difficulty: "hard" }, " French ")).toEqual({
      count: 50,
      difficulty: "hard",
      language: "French",
    });
  });

  it("only offers settings that exist for the selected generator", () => {
    const glossary = GENERATORS.find((g) => g.type === "glossary")!;
    expect(glossary.fields.map((f) => f.key)).toEqual(["max_terms"]);
  });
});

describe("safe LaTeX rendering", () => {
  it("renders valid LaTeX with KaTeX", () => {
    render(<Latex expression="E = mc^2" />);
    expect(screen.getByTestId("latex").querySelector(".katex")).not.toBeNull();
  });

  it("never turns hostile input into HTML or links", () => {
    const hostile = String.raw`\href{javascript:alert(1)}{x}<img src=x onerror=alert(1)><script>alert(1)</script>`;
    render(<Latex expression={hostile} />);
    const el = screen.getByTestId("latex");
    expect(el.querySelector("script")).toBeNull();
    expect(el.querySelector("img")).toBeNull();
    expect(el.querySelector("a[href]")).toBeNull();
  });

  it("shows unparseable input as plain text", () => {
    render(<Latex expression={String.raw`\frac{1`} />);
    const el = screen.getByTestId("latex");
    expect(el.dataset.latexError).toBe("true");
    expect(el.textContent).toBe(String.raw`\frac{1`);
  });
});

describe("formula sheet", () => {
  it("always says the formulas are not verified and flags review items", () => {
    render(
      <FormulaView
        sources={[]}
        unavailable={[]}
        payload={{
          title: "F",
          flagged_count: 1,
          formulas: [
            {
              name: "Energy",
              expression: "E=mc^2",
              needs_review: true,
              review_notes: ["undefined variable"],
            },
          ],
        }}
      />,
    );
    expect(screen.getByRole("note")).toHaveTextContent(/not verified/i);
    expect(screen.getByRole("status")).toHaveTextContent(/undefined variable/);
  });
});

describe("source references", () => {
  const sources = [
    { rank: 1, kind: "chunk" as const, document_id: "d1", page_number: 4 },
    { rank: 2, kind: "chunk" as const, document_id: "gone", page_number: 2 },
  ];
  it("links to the document page and marks deleted documents as unavailable", () => {
    render(<SourceRefs refs={[1, 2]} sources={sources} unavailable={["gone"]} />);
    expect(screen.getByRole("link", { name: /Page 4/ })).toHaveAttribute(
      "href",
      "/documents/d1?page=4",
    );
    expect(screen.getByText(/Source unavailable/)).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });
  it("renders nothing for references that map to no source", () => {
    const { container } = render(<SourceRefs refs={[9]} sources={sources} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("payload editor", () => {
  it("edits text but never offers backend-owned fields", async () => {
    const onChange = vi.fn();
    render(
      <PayloadEditor
        value={{
          title: "Old",
          sections: [{ heading: "H", kind: "concept", body: "B", source_refs: [1] }],
        }}
        onChange={onChange}
      />,
    );
    expect(screen.queryByLabelText(/source refs/i)).toBeNull();
    expect(screen.queryByLabelText(/^kind$/i)).toBeNull();
    await userEvent.type(screen.getByLabelText("Title"), "!");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ title: "Old!" }));
  });
});

describe("export formats", () => {
  it("matches what the backend supports and offers none for unknown types", () => {
    expect(EXPORT_FORMATS.quiz).toEqual(["pdf"]);
    expect(EXPORT_FORMATS.flashcards).toEqual(["csv", "pdf"]);
    expect(EXPORT_FORMATS.nope).toBeUndefined();
  });
});

describe("flashcard study mode", () => {
  const card = (n: number): Flashcard =>
    ({
      id: `c${n}`,
      front: `Front ${n}?`,
      back: `Back ${n}`,
      explanation: null,
      card_type: "basic",
      difficulty: "easy",
      source_references: [],
      display_order: n,
      is_favourite: false,
      origin: "generated",
      revision: 1,
    }) as unknown as Flashcard;

  it("flips, navigates and reports progress", async () => {
    render(<StudyMode cards={[card(1), card(2)]} unavailable={[]} />);
    expect(screen.getByText("Card 1 of 2")).toBeInTheDocument();
    expect(screen.getByTestId("flashcard-face")).toHaveTextContent("Front 1?");
    await userEvent.click(screen.getByTestId("flashcard-face"));
    expect(screen.getByTestId("flashcard-face")).toHaveTextContent("Back 1");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Card 2 of 2")).toBeInTheDocument();
    expect(screen.getByTestId("flashcard-face")).toHaveTextContent("Front 2?");
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("shuffles without losing or duplicating cards", () => {
    const items = [1, 2, 3, 4, 5, 6];
    const out = shuffled(items, () => 0.3);
    expect([...out].sort()).toEqual(items);
  });

  it("says so when the deck is empty", () => {
    render(<StudyMode cards={[]} unavailable={[]} />);
    expect(screen.getByText(/no cards yet/i)).toBeInTheDocument();
  });
});

describe("quiz helpers", () => {
  it("formats the countdown", () => {
    expect(formatClock(65)).toBe("01:05");
    expect(formatClock(3725)).toBe("1:02:05");
    expect(formatClock(-3)).toBe("00:00");
  });
  it("treats empty and whitespace answers as unanswered", () => {
    expect(isAnswered([])).toBe(false);
    expect(isAnswered("  ")).toBe(false);
    expect(isAnswered(["A"])).toBe(true);
    expect(isAnswered("text")).toBe(true);
  });
});

describe("QuizTaker", () => {
  const attempt = (over: Partial<QuizAttempt> = {}): QuizAttempt =>
    ({
      id: "a1",
      quiz_id: "q1",
      status: "in_progress",
      started_at: "2026-01-01T00:00:00Z",
      expires_at: null,
      server_time: "2026-01-01T00:00:10Z",
      seconds_remaining: null,
      submitted_at: null,
      auto_submitted: false,
      question_order: ["x1", "x2"],
      answers: {},
      flagged: [],
      questions: [
        {
          id: "x1",
          question: "Pick the powerhouse of the cell",
          question_type: "multiple_choice",
          difficulty: "easy",
          answer_format: "single_choice",
          options: [
            { id: "A", text: "Mitochondria" },
            { id: "B", text: "Nucleus" },
          ],
          display_order: 0,
        },
        {
          id: "x2",
          question: "Explain osmosis in your own words",
          question_type: "short_answer",
          difficulty: "easy",
          answer_format: "text",
          options: [],
          display_order: 1,
        },
      ],
      score: null,
      total_questions: null,
      graded_questions: null,
      percentage: null,
      ...over,
    }) as QuizAttempt;

  beforeEach(() => {
    vi.resetAllMocks();
    api.get.mockResolvedValue({ id: "m1", item_id: "q1" } as StudyMaterial);
    api.saveAnswers.mockResolvedValue(attempt());
    api.submit.mockResolvedValue(attempt({ status: "submitted" }));
  });
  afterEach(() => vi.useRealTimers());

  it("shows questions with no answer key, and resumes saved answers after a refresh", async () => {
    api.startAttempt.mockResolvedValue(attempt({ answers: { x1: ["B"] } }));
    render(<QuizTaker materialId="m1" />);
    expect(await screen.findByText(/Pick the powerhouse/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Nucleus/ })).toBeChecked();
    expect(screen.queryByText(/correct answer/i)).toBeNull();
    expect(screen.queryByText(/explanation/i)).toBeNull();
    expect(screen.getByText("1 of 2 answered")).toBeInTheDocument();
  });

  it("autosaves a changed answer", async () => {
    api.startAttempt.mockResolvedValue(attempt());
    render(<QuizTaker materialId="m1" />);
    await userEvent.click(await screen.findByRole("radio", { name: /Mitochondria/ }));
    await waitFor(() => expect(api.saveAnswers).toHaveBeenCalled(), { timeout: 3000 });
    expect(api.saveAnswers.mock.calls[0][2]).toEqual([{ question_id: "x1", answer: ["A"] }]);
    await waitFor(() => expect(screen.getByTestId("save-state")).toHaveTextContent("saved"));
  });

  it("flags a question and saves the flag", async () => {
    api.startAttempt.mockResolvedValue(attempt());
    render(<QuizTaker materialId="m1" />);
    await userEvent.click(await screen.findByRole("button", { name: /Flag for review/ }));
    await waitFor(() => expect(api.saveAnswers).toHaveBeenCalled(), { timeout: 3000 });
    expect(api.saveAnswers.mock.calls[0][3]).toEqual(["x1"]);
  });

  it("warns about unanswered questions before submitting, then goes to the results", async () => {
    api.startAttempt.mockResolvedValue(attempt());
    render(<QuizTaker materialId="m1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Submit quiz" }));
    expect(await screen.findByText(/2 unanswered questions/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/study/m1/quiz/results/a1"));
  });

  it("auto-submits when the server deadline passes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    api.startAttempt.mockResolvedValue(attempt({ seconds_remaining: 2 }));
    render(<QuizTaker materialId="m1" />);
    expect(await screen.findByTestId("quiz-timer")).toHaveTextContent("00:02");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2600);
    });
    await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/study/m1/quiz/results/a1?timeup=1"));
  });

  it("goes to the results when the server says the attempt already ended", async () => {
    api.startAttempt.mockResolvedValue(attempt());
    api.saveAnswers.mockRejectedValue(new ApiRequestError("QUIZ_ATTEMPT_EXPIRED", "expired", 409));
    render(<QuizTaker materialId="m1" />);
    await userEvent.click(await screen.findByRole("radio", { name: /Mitochondria/ }));
    await waitFor(() => expect(api.submit).toHaveBeenCalled(), { timeout: 3000 });
    await waitFor(() => expect(push).toHaveBeenCalled());
  });

  it("redirects to the results when the returned attempt is already submitted", async () => {
    api.startAttempt.mockResolvedValue(attempt({ status: "submitted", questions: [] }));
    render(<QuizTaker materialId="m1" />);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/study/m1/quiz/results/a1"));
  });
});
