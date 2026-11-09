import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ChatInput } from "./chat-input";
import { noticeText } from "./dialogs";
import { MessageView } from "./message-view";
import type { ChatItem } from "./use-chat";
import { groupConversations, groupLabel } from "./use-conversations";
import { SUGGESTED_PROMPTS, Welcome } from "./welcome";

function Harness(props: Partial<React.ComponentProps<typeof ChatInput>> & { onSend?: () => void }) {
  const [value, setValue] = useState(props.value ?? "");
  return (
    <ChatInput
      value={value}
      onChange={setValue}
      onSend={props.onSend ?? vi.fn()}
      onStop={props.onStop ?? vi.fn()}
      generating={props.generating ?? false}
      maxChars={props.maxChars ?? 50}
    />
  );
}

describe("ChatInput", () => {
  it("sends on Enter and keeps Shift+Enter for a new line", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);
    const box = screen.getByRole("textbox", { name: /message the ai tutor/i });
    await userEvent.type(box, "hello");
    await userEvent.keyboard("{Shift>}{Enter}{/Shift}");
    expect(onSend).not.toHaveBeenCalled();
    expect(box).toHaveValue("hello\n");
    await userEvent.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("does not send an empty or whitespace-only message", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);
    await userEvent.type(screen.getByRole("textbox"), "   {Enter}");
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("shows Stop instead of Send while generating and ignores Enter", async () => {
    const onSend = vi.fn();
    const onStop = vi.fn();
    render(<Harness onSend={onSend} onStop={onStop} generating value="next question" />);
    expect(screen.queryByRole("button", { name: /^send/i })).not.toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox"), "{Enter}");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /stop/i }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("matches the backend limit: counter, warning and blocked send", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} maxChars={10} value={"x".repeat(11)} />);
    expect(screen.getByText(/11 \/ 10/)).toHaveTextContent("too long");
    expect(screen.getByRole("textbox")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "{Enter}");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("describes the shortcuts to assistive technology", () => {
    render(<Harness />);
    expect(screen.getByRole("textbox")).toHaveAccessibleDescription(/enter to send.*shift\+enter/i);
  });
});

const item = (over: Partial<ChatItem>): ChatItem => ({
  key: "k",
  id: "m1",
  role: "assistant",
  content: "Answer",
  status: "completed",
  errorCode: null,
  citations: [],
  ...over,
});

function view(i: ChatItem, over: Partial<React.ComponentProps<typeof MessageView>> = {}) {
  const props = {
    item: i,
    isLatestAssistant: true,
    busy: false,
    error: null,
    rating: null,
    onRegenerate: vi.fn(),
    onRate: vi.fn(),
    ...over,
  };
  render(
    <ol>
      <MessageView {...props} />
    </ol>,
  );
  return props;
}

describe("MessageView", () => {
  it("shows the user's text literally, never as HTML or markdown", () => {
    view(item({ role: "user", content: "<b>bold</b> **x** <img src=x onerror=alert(1)>" }));
    expect(document.querySelector("b")).toBeNull();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText(/<b>bold<\/b>/)).toBeInTheDocument();
  });

  it("renders assistant markdown and offers copy, regenerate and feedback", async () => {
    const p = view(item({ content: "**Hi** there" }));
    expect(document.querySelector("strong")).toHaveTextContent("Hi");
    expect(screen.getByRole("button", { name: /copy/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(p.onRegenerate).toHaveBeenCalledWith("m1");
    await userEvent.click(screen.getByRole("button", { name: "Good response" }));
    expect(p.onRate).toHaveBeenCalledWith("m1", "positive");
    await userEvent.click(screen.getByRole("button", { name: "Bad response" }));
    expect(p.onRate).toHaveBeenCalledWith("m1", "negative");
  });

  it("reflects the chosen rating with aria-pressed", () => {
    view(item({}), { rating: "negative" });
    expect(screen.getByRole("button", { name: "Bad response" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Good response" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("only the latest answer can be regenerated, and not while busy", () => {
    view(item({}), { isLatestAssistant: false });
    expect(screen.queryByRole("button", { name: /regenerate/i })).not.toBeInTheDocument();
  });

  it("disables regenerate while another answer is generating", () => {
    view(item({}), { busy: true });
    expect(screen.getByRole("button", { name: /regenerate/i })).toBeDisabled();
  });

  it("shows a thinking state before the first token, with no actions", () => {
    view(item({ status: "pending", content: "", id: null }));
    expect(screen.getByText(/thinking/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /copy/i })).not.toBeInTheDocument();
    expect(screen.getByRole("article")).toHaveAttribute("aria-busy", "true");
  });

  it("keeps partial text on a failed answer and offers Retry with the reason", async () => {
    const p = view(item({ status: "failed", content: "Partial te" }), {
      error: { code: "LLM_TIMEOUT", message: "The AI took too long.", retryable: true },
    });
    expect(screen.getByText(/partial te/i)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("The AI took too long.");
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(p.onRegenerate).toHaveBeenCalledWith("m1");
    expect(screen.queryByRole("button", { name: "Good response" })).not.toBeInTheDocument();
  });

  it("marks a stopped answer as stopped, not as an error", () => {
    view(item({ status: "cancelled", content: "Half" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/stopped/i);
    expect(screen.getByRole("button", { name: /regenerate/i })).toBeInTheDocument();
  });
});

describe("Welcome", () => {
  it("offers the five spec prompts and sends the real prompt text", async () => {
    const onPick = vi.fn();
    render(<Welcome onPick={onPick} disabled={false} />);
    expect(screen.getByRole("heading", { name: "Welcome to Axonweave AI" })).toBeInTheDocument();
    expect(screen.getByText("Your personal academic learning companion.")).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(SUGGESTED_PROMPTS.length);
    await userEvent.click(screen.getByRole("button", { name: "Compare two technical concepts" }));
    expect(onPick).toHaveBeenCalledWith(SUGGESTED_PROMPTS[2].prompt);
  });

  it("disables the prompts while a request is running", () => {
    render(<Welcome onPick={vi.fn()} disabled />);
    for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
  });
});

describe("conversation grouping", () => {
  const now = new Date(2026, 10, 6, 12);
  it("buckets by calendar day", () => {
    expect(groupLabel(new Date(2026, 10, 6, 1).toISOString(), now)).toBe("Today");
    expect(groupLabel(new Date(2026, 10, 5, 23).toISOString(), now)).toBe("Yesterday");
    expect(groupLabel(new Date(2026, 10, 1).toISOString(), now)).toBe("Previous 7 days");
    expect(groupLabel(new Date(2026, 9, 1).toISOString(), now)).toBe("Older");
  });

  it("keeps the server's order and merges neighbours", () => {
    const mk = (id: string, d: Date) =>
      ({ id, last_message_at: d.toISOString(), created_at: d.toISOString() }) as never;
    const groups = groupConversations(
      [
        mk("a", new Date(2026, 10, 6)),
        mk("b", new Date(2026, 10, 6)),
        mk("c", new Date(2026, 9, 1)),
      ],
      now,
    );
    expect(groups.map((g) => [g.label, g.items.length])).toEqual([
      ["Today", 2],
      ["Older", 1],
    ]);
  });
});

describe("privacy notice text (D-54)", () => {
  const status = {
    configured: true,
    provider_display_name: "Acme AI",
    is_test_provider: false,
    max_input_chars: 8000,
  };

  it("names the provider from configuration and says data leaves the server", () => {
    expect(noticeText(status)).toContain("Acme AI");
    expect(noticeText(status)).toMatch(/sent to/i);
  });

  it("does not claim data is sent anywhere for the test provider", () => {
    const text = noticeText({
      ...status,
      provider_display_name: "Test provider",
      is_test_provider: true,
    });
    expect(text).toMatch(/not a real AI/i);
    expect(text).toMatch(/nothing is sent/i);
  });
});
