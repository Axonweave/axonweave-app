import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError, api } from "@/lib/api/client";
import LoginPage from "./login/page";
import RegisterPage from "./register/page";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/login",
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return { ...actual, api: { ...actual.api, post: vi.fn() } };
});

const post = vi.mocked(api.post);

beforeEach(() => {
  vi.resetAllMocks();
});

describe("LoginPage", () => {
  it("shows field errors and sends nothing when submitted empty", async () => {
    render(<LoginPage />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("rejects a malformed email", async () => {
    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "not-an-email");
    await userEvent.type(screen.getByLabelText("Password"), "whatever");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("posts credentials and goes to the dashboard on success", async () => {
    post.mockResolvedValue({ success: true, data: null });
    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/dashboard"));
    expect(post).toHaveBeenCalledWith(
      "/auth/login",
      expect.objectContaining({ email: "ada@example.com", password: "correct horse battery" }),
    );
  });

  it("shows the server's message when login fails and does not navigate", async () => {
    post.mockRejectedValue(
      new ApiRequestError("INVALID_CREDENTIALS", "Invalid email or password.", 401),
    );
    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Invalid email or password.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("falls back to a generic message for unexpected errors", async () => {
    post.mockRejectedValue(new Error("network down"));
    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText(/unexpected error/i)).toBeInTheDocument();
  });

  it("links to registration and password reset", () => {
    render(<LoginPage />);
    expect(screen.getByRole("link", { name: "Create one" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });
});

describe("RegisterPage", () => {
  async function fill(
    overrides: Partial<Record<"name" | "email" | "pw" | "confirm", string>> = {},
  ) {
    await userEvent.type(screen.getByLabelText("Full name"), overrides.name ?? "Ada Lovelace");
    await userEvent.type(screen.getByLabelText("Email"), overrides.email ?? "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), overrides.pw ?? "a-long-enough-pass");
    await userEvent.type(
      screen.getByLabelText("Confirm password"),
      overrides.confirm ?? "a-long-enough-pass",
    );
  }

  it("requires every field and the terms checkbox", async () => {
    render(<RegisterPage />);
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Full name is required")).toBeInTheDocument();
    expect(
      screen.getByText(/at least 12 characters/i, { selector: "p.text-destructive" }),
    ).toBeInTheDocument();
    expect(screen.getByText("You must accept the terms to create an account")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("flags a password shorter than 12 characters", async () => {
    render(<RegisterPage />);
    await fill({ pw: "short", confirm: "short" });
    await userEvent.click(screen.getByLabelText(/I agree/));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Password must be at least 12 characters")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("flags mismatched passwords", async () => {
    render(<RegisterPage />);
    await fill({ confirm: "a-different-long-pass" });
    await userEvent.click(screen.getByLabelText(/I agree/));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("submits a valid form to the register endpoint", async () => {
    post.mockResolvedValue({ success: true, data: null });
    render(<RegisterPage />);
    await fill();
    await userEvent.click(screen.getByLabelText(/I agree/));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith(
      "/auth/register",
      expect.objectContaining({
        full_name: "Ada Lovelace",
        email: "ada@example.com",
        terms_accepted: true,
      }),
    );
    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByText(/ada@example.com/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to sign in" })).toHaveAttribute("href", "/login");
  });

  it("shows the server error, for example a duplicate email", async () => {
    post.mockRejectedValue(
      new ApiRequestError("EMAIL_ALREADY_REGISTERED", "That email is already registered.", 409),
    );
    render(<RegisterPage />);
    await fill();
    await userEvent.click(screen.getByLabelText(/I agree/));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("That email is already registered.")).toBeInTheDocument();
  });
});
