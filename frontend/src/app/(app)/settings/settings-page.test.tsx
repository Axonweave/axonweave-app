import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/lib/api/client";
import { profileApi } from "@/lib/api/profile";
import SettingsPage from "./page";

const toast = vi.fn();
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast }) }));

const refresh = vi.fn();
const authState = vi.hoisted(() => ({ user: { is_verified: true } as { is_verified: boolean } }));
vi.mock("@/contexts/auth-context", () => ({
  useAuthContext: () => ({ user: authState.user, loading: false, refresh }),
}));

vi.mock("@/lib/api/profile", () => ({
  profileApi: {
    getPreferences: vi.fn(),
    updatePreferences: vi.fn(),
    changePassword: vi.fn(),
    changeEmail: vi.fn(),
    getSessions: vi.fn(),
    revokeSession: vi.fn(),
    exportData: vi.fn(),
    deleteAccount: vi.fn(),
  },
}));

const api = vi.mocked(profileApi);
const ok = { success: true as const, data: null };

async function openTab(name: string) {
  await userEvent.click(screen.getByRole("tab", { name }));
}

beforeEach(() => {
  vi.resetAllMocks();
  authState.user = { is_verified: true };
  api.getPreferences.mockResolvedValue({
    success: true,
    data: { theme: "system", explanation_style: null, academic_level: null },
  } as never);
});

describe("SettingsPage structure", () => {
  it("exposes the sections as an accessible tab list", async () => {
    render(<SettingsPage />);
    expect(screen.getByRole("tablist", { name: "Settings sections" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(6);
    expect(screen.getByRole("tab", { name: "Appearance" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await openTab("Security");
    expect(screen.getByRole("tab", { name: "Security" })).toHaveAttribute("aria-selected", "true");
  });
});

describe("Appearance", () => {
  it("saves the chosen theme", async () => {
    api.updatePreferences.mockResolvedValue({ success: true, data: { theme: "dark" } } as never);
    render(<SettingsPage />);
    await userEvent.click(await screen.findByRole("button", { name: /dark/i }));
    await waitFor(() => expect(api.updatePreferences).toHaveBeenCalledWith({ theme: "dark" }));
    expect(toast).toHaveBeenCalledWith({ title: "Appearance saved" });
  });

  it("reports a save failure", async () => {
    api.updatePreferences.mockRejectedValue(new Error("x"));
    render(<SettingsPage />);
    await userEvent.click(await screen.findByRole("button", { name: /light/i }));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(expect.objectContaining({ variant: "destructive" })),
    );
  });
});

describe("Security: change password", () => {
  async function fillPasswords(current: string, next: string, confirm: string) {
    await userEvent.type(
      screen.getByLabelText("Current password", { selector: "#current-password" }),
      current,
    );
    await userEvent.type(screen.getByLabelText("New password"), next);
    await userEvent.type(screen.getByLabelText("Confirm new password"), confirm);
  }

  it("refuses mismatched passwords without calling the API", async () => {
    render(<SettingsPage />);
    await openTab("Security");
    await fillPasswords("old-password-1", "a-long-enough-pass", "a-different-long-pass");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Passwords do not match", variant: "destructive" }),
    );
    expect(api.changePassword).not.toHaveBeenCalled();
  });

  it("sends the current and new password and clears the form on success", async () => {
    api.changePassword.mockResolvedValue(ok);
    render(<SettingsPage />);
    await openTab("Security");
    await fillPasswords("old-password-1", "a-long-enough-pass", "a-long-enough-pass");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    await waitFor(() =>
      expect(api.changePassword).toHaveBeenCalledWith({
        current_password: "old-password-1",
        new_password: "a-long-enough-pass",
      }),
    );
    expect(toast).toHaveBeenCalledWith({ title: "Password changed successfully" });
    expect(screen.getByLabelText("New password")).toHaveValue("");
  });

  it("shows the server's reason when the current password is wrong", async () => {
    api.changePassword.mockRejectedValue(
      new ApiRequestError("INVALID_PASSWORD", "Current password is incorrect.", 400),
    );
    render(<SettingsPage />);
    await openTab("Security");
    await fillPasswords("bad", "a-long-enough-pass", "a-long-enough-pass");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith({
        title: "Error",
        description: "Current password is incorrect.",
        variant: "destructive",
      }),
    );
  });
});

describe("Security: change email", () => {
  it("requests the change with the current password", async () => {
    api.changeEmail.mockResolvedValue(ok);
    render(<SettingsPage />);
    await openTab("Security");
    await userEvent.type(
      screen.getByLabelText("Current password", { selector: "#email-password" }),
      "an example passphrase",
    );
    await userEvent.type(screen.getByLabelText("New email address"), "new@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Request email change" }));
    await waitFor(() =>
      expect(api.changeEmail).toHaveBeenCalledWith({
        current_password: "an example passphrase",
        new_email: "new@example.com",
      }),
    );
  });
});

describe("Sessions", () => {
  const sessions = [
    {
      id: "s1",
      user_agent: "Firefox",
      ip_address: "1.1.1.1",
      last_used_at: "2026-11-04T10:00:00Z",
      is_current: true,
    },
    {
      id: "s2",
      user_agent: "Chrome",
      ip_address: "2.2.2.2",
      last_used_at: "2026-11-03T10:00:00Z",
      is_current: false,
    },
  ];

  it("lists sessions, marks the current one, and only lets you revoke others", async () => {
    api.getSessions.mockResolvedValue({ success: true, data: sessions } as never);
    api.revokeSession.mockResolvedValue(ok);
    render(<SettingsPage />);
    await openTab("Sessions");
    expect(await screen.findByText("Current")).toBeInTheDocument();
    const buttons = screen.getAllByRole("button", { name: /revoke|sign out/i });
    expect(buttons).toHaveLength(1);
    await userEvent.click(buttons[0]);
    await waitFor(() => expect(api.revokeSession).toHaveBeenCalledWith("s2"));
    await waitFor(() => expect(screen.queryByText("Chrome")).not.toBeInTheDocument());
  });

  it("shows an empty message", async () => {
    api.getSessions.mockResolvedValue({ success: true, data: [] } as never);
    render(<SettingsPage />);
    await openTab("Sessions");
    expect(await screen.findByText("No sessions found.")).toBeInTheDocument();
  });

  it("reports a load failure", async () => {
    api.getSessions.mockRejectedValue(new Error("x"));
    render(<SettingsPage />);
    await openTab("Sessions");
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({ title: "Could not load sessions" }),
      ),
    );
  });
});

describe("Account: export and deletion", () => {
  it("disables export and delete until the email is verified", async () => {
    authState.user = { is_verified: false };
    render(<SettingsPage />);
    await openTab("Account");
    expect(screen.getByRole("button", { name: "Export data" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete account" })).toBeDisabled();
    expect(screen.getByText(/verification required to export/i)).toBeInTheDocument();
  });

  it("sends the exact contract the API expects when deleting the account", async () => {
    api.deleteAccount.mockResolvedValue(ok);
    render(<SettingsPage />);
    await openTab("Account");
    await userEvent.click(screen.getByRole("button", { name: "Delete account" }));

    const confirm = screen.getByRole("button", { name: "Delete my account" });
    expect(confirm).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Current password"), "my-password-123");
    await userEvent.type(screen.getByLabelText(/to confirm/i), "delete my account");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);

    await waitFor(() =>
      expect(api.deleteAccount).toHaveBeenCalledWith({
        password: "my-password-123",
        confirmation: "delete my account",
      }),
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("does not allow deletion with the wrong confirmation phrase", async () => {
    render(<SettingsPage />);
    await openTab("Account");
    await userEvent.click(screen.getByRole("button", { name: "Delete account" }));
    await userEvent.type(screen.getByLabelText("Current password"), "my-password-123");
    await userEvent.type(screen.getByLabelText(/to confirm/i), "DELETE");
    expect(screen.getByRole("button", { name: "Delete my account" })).toBeDisabled();
    expect(api.deleteAccount).not.toHaveBeenCalled();
  });

  it("surfaces a rejected deletion and stays signed in", async () => {
    api.deleteAccount.mockRejectedValue(
      new ApiRequestError("INVALID_PASSWORD", "Incorrect password.", 400),
    );
    render(<SettingsPage />);
    await openTab("Account");
    await userEvent.click(screen.getByRole("button", { name: "Delete account" }));
    await userEvent.type(screen.getByLabelText("Current password"), "nope");
    await userEvent.type(screen.getByLabelText(/to confirm/i), "delete my account");
    await userEvent.click(screen.getByRole("button", { name: "Delete my account" }));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({ description: "Incorrect password." }),
      ),
    );
    expect(refresh).not.toHaveBeenCalled();
  });

  it("downloads the export through the API", async () => {
    api.exportData.mockResolvedValue({ success: true, data: { profile: {} } } as never);
    const createObjectURL = vi.fn(() => "blob:x");
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL: vi.fn() });
    render(<SettingsPage />);
    await openTab("Account");
    await userEvent.click(screen.getByRole("button", { name: "Export data" }));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    vi.unstubAllGlobals();
  });
});
