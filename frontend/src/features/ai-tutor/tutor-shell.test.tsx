import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { conversationIdFromPath, TutorShell } from "./tutor-shell";

const mocks = vi.hoisted(() => ({
  status: vi.fn(),
  models: vi.fn(),
  preferences: vi.fn(),
  acknowledgeNotice: vi.fn(),
  listConversations: vi.fn(),
  pathname: { current: "/ai-tutor" },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname.current,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("@/lib/api/ai", () => ({
  aiApi: {
    status: mocks.status,
    models: mocks.models,
    preferences: mocks.preferences,
    acknowledgeNotice: mocks.acknowledgeNotice,
    listConversations: mocks.listConversations,
    listMessages: vi.fn().mockResolvedValue([]),
    getConversation: vi.fn(),
  },
}));

const CONFIGURED = {
  configured: true,
  provider_display_name: "Acme AI",
  is_test_provider: false,
  max_input_chars: 8000,
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.pathname.current = "/ai-tutor";
  mocks.models.mockResolvedValue([]);
  mocks.listConversations.mockResolvedValue({ data: [], total: 0, limit: 30, offset: 0 });
  mocks.preferences.mockResolvedValue({ ai_notice_acknowledged_at: "2026-01-01T00:00:00Z" });
});

describe("conversationIdFromPath", () => {
  it("reads the id from the URL", () => {
    expect(conversationIdFromPath("/ai-tutor")).toBeNull();
    expect(conversationIdFromPath("/ai-tutor/")).toBeNull();
    expect(conversationIdFromPath("/ai-tutor/abc-123")).toBe("abc-123");
    expect(conversationIdFromPath("/ai-tutor/abc-123/")).toBe("abc-123");
    expect(conversationIdFromPath("/subjects/abc")).toBeNull();
  });
});

describe("TutorShell gates", () => {
  it("shows a clear 'not configured' state and never asks for models or conversations (D-58)", async () => {
    mocks.status.mockResolvedValue({
      ...CONFIGURED,
      configured: false,
      provider_display_name: null,
    });
    render(<TutorShell />);
    expect(await screen.findByText("AI is not configured")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to dashboard/i })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(mocks.models).not.toHaveBeenCalled();
    expect(mocks.listConversations).not.toHaveBeenCalled();
  });

  it("blocks the tutor behind the privacy notice until it is acknowledged (D-54)", async () => {
    mocks.status.mockResolvedValue(CONFIGURED);
    mocks.preferences.mockResolvedValue({ ai_notice_acknowledged_at: null });
    mocks.acknowledgeNotice.mockResolvedValue({
      ai_notice_acknowledged_at: "2026-11-06T00:00:00Z",
    });
    render(<TutorShell />);

    const dialog = await screen.findByRole("dialog", { name: /before you start/i });
    expect(dialog).toHaveTextContent("Acme AI"); // provider named from configuration
    await userEvent.click(screen.getByRole("button", { name: /i understand/i }));
    expect(mocks.acknowledgeNotice).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /before you start/i })).not.toBeInTheDocument(),
    );
  });

  it("keeps the notice open and says so when saving the acknowledgement fails", async () => {
    mocks.status.mockResolvedValue(CONFIGURED);
    mocks.preferences.mockResolvedValue({ ai_notice_acknowledged_at: null });
    mocks.acknowledgeNotice.mockRejectedValue(new Error("down"));
    render(<TutorShell />);
    await userEvent.click(await screen.findByRole("button", { name: /i understand/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not save/i);
    expect(screen.getByRole("dialog", { name: /before you start/i })).toBeInTheDocument();
  });

  it("does not show the notice again once acknowledged, and renders the chat", async () => {
    mocks.status.mockResolvedValue(CONFIGURED);
    render(<TutorShell />);
    expect(
      await screen.findByRole("heading", { name: "Welcome to Axonweave AI" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /before you start/i })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message the ai tutor/i })).toBeInTheDocument();
  });

  it("offers a retry when the status cannot be loaded", async () => {
    mocks.status.mockRejectedValueOnce(new Error("offline")).mockResolvedValue(CONFIGURED);
    render(<TutorShell />);
    await userEvent.click(await screen.findByRole("button", { name: /try again/i }));
    expect(
      await screen.findByRole("heading", { name: "Welcome to Axonweave AI" }),
    ).toBeInTheDocument();
  });

  it("only offers a model selector when there is more than one model", async () => {
    mocks.status.mockResolvedValue(CONFIGURED);
    const model = (id: string, d: boolean) => ({ id, display_name: id, is_default: d });
    mocks.models.mockResolvedValue([model("one", true)]);
    const { unmount } = render(<TutorShell />);
    await screen.findByRole("heading", { name: "Welcome to Axonweave AI" });
    expect(screen.queryByLabelText("Model")).not.toBeInTheDocument();
    unmount();

    mocks.models.mockResolvedValue([model("one", true), model("two", false)]);
    render(<TutorShell />);
    expect(await screen.findByLabelText("Model")).toBeInTheDocument();
  });
});
