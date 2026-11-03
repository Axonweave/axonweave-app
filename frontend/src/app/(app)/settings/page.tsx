"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/hooks/use-toast";
import { useAuthContext } from "@/contexts/auth-context";
import { profileApi } from "@/lib/api/profile";
import { ApiRequestError } from "@/lib/api/client";
import type { SessionInfo, UserPreferences } from "@/types/api";

type Tab = "appearance" | "learning" | "security" | "sessions" | "account";

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

function AppearanceTab() {
  const { toast } = useToast();
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    profileApi.getPreferences().then((r) => setPrefs(r.data)).catch(() => {});
  }, []);

  async function save(theme: "light" | "dark" | "system") {
    setSaving(true);
    try {
      const r = await profileApi.updatePreferences({ theme });
      setPrefs(r.data);
      toast({ title: "Appearance saved" });
    } catch {
      toast({ title: "Error", description: "Could not save appearance.", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  }

  const themes: Array<{ value: "light" | "dark" | "system"; label: string }> = [
    { value: "light", label: "Light" },
    { value: "dark", label: "Dark" },
    { value: "system", label: "System" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">Theme</h2>
        <p className="text-sm text-muted-foreground">Choose how Axonweave looks to you.</p>
      </div>
      <div className="flex gap-3">
        {themes.map((t) => (
          <button
            key={t.value}
            type="button"
            disabled={saving}
            onClick={() => save(t.value)}
            className={`rounded-lg border-2 px-4 py-2 text-sm font-medium transition-colors ${
              prefs?.theme === t.value
                ? "border-primary text-primary"
                : "border-border text-muted-foreground hover:border-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function LearningTab() {
  const { toast } = useToast();
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    profileApi.getPreferences().then((r) => setPrefs(r.data)).catch(() => {});
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!prefs) return;
    setSaving(true);
    try {
      const r = await profileApi.updatePreferences({
        explanation_style: prefs.explanation_style,
        academic_level: prefs.academic_level,
      });
      setPrefs(r.data);
      toast({ title: "Learning preferences saved" });
    } catch {
      toast({ title: "Error", description: "Could not save preferences.", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  }

  if (!prefs) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <form onSubmit={handleSave} className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">Learning preferences</h2>
        <p className="text-sm text-muted-foreground">These will guide AI explanations in future phases.</p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="explanation-style">Explanation style</Label>
        <select
          id="explanation-style"
          value={prefs.explanation_style ?? ""}
          onChange={(e) => setPrefs({ ...prefs, explanation_style: e.target.value || null })}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">Not set</option>
          <option value="concise">Concise</option>
          <option value="detailed">Detailed</option>
          <option value="visual">Visual / analogies</option>
          <option value="step_by_step">Step-by-step</option>
        </select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="academic-level">Academic level</Label>
        <select
          id="academic-level"
          value={prefs.academic_level ?? ""}
          onChange={(e) => setPrefs({ ...prefs, academic_level: e.target.value || null })}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">Not set</option>
          <option value="secondary">Secondary school</option>
          <option value="undergraduate">Undergraduate</option>
          <option value="postgraduate">Postgraduate</option>
          <option value="professional">Professional</option>
        </select>
      </div>
      <Button type="submit" disabled={saving}>
        {saving ? "Saving…" : "Save preferences"}
      </Button>
    </form>
  );
}

function SecurityTab() {
  const { toast } = useToast();
  const [pwForm, setPwForm] = useState({ current: "", next: "", confirm: "" });
  const [emailForm, setEmailForm] = useState({ password: "", newEmail: "" });
  const [savingPw, setSavingPw] = useState(false);
  const [savingEmail, setSavingEmail] = useState(false);

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (pwForm.next !== pwForm.confirm) {
      toast({ title: "Passwords do not match", variant: "destructive" });
      return;
    }
    setSavingPw(true);
    try {
      await profileApi.changePassword({ current_password: pwForm.current, new_password: pwForm.next });
      setPwForm({ current: "", next: "", confirm: "" });
      toast({ title: "Password changed successfully" });
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Could not change password.";
      toast({ title: "Error", description: msg, variant: "destructive" });
    } finally {
      setSavingPw(false);
    }
  }

  async function handleChangeEmail(e: React.FormEvent) {
    e.preventDefault();
    setSavingEmail(true);
    try {
      await profileApi.changeEmail({ current_password: emailForm.password, new_email: emailForm.newEmail });
      setEmailForm({ password: "", newEmail: "" });
      toast({ title: "Verification email sent", description: "Check your new email address to confirm the change." });
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Could not request email change.";
      toast({ title: "Error", description: msg, variant: "destructive" });
    } finally {
      setSavingEmail(false);
    }
  }

  return (
    <div className="space-y-8">
      {/* Change password */}
      <form onSubmit={handleChangePassword} className="space-y-4">
        <div>
          <h2 className="text-base font-semibold">Change password</h2>
          <p className="text-sm text-muted-foreground">Changing your password signs you out of all other sessions.</p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="current-password">Current password</Label>
          <Input
            id="current-password"
            type="password"
            value={pwForm.current}
            onChange={(e) => setPwForm((f) => ({ ...f, current: e.target.value }))}
            required
            autoComplete="current-password"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="new-password">New password</Label>
          <Input
            id="new-password"
            type="password"
            value={pwForm.next}
            onChange={(e) => setPwForm((f) => ({ ...f, next: e.target.value }))}
            required
            minLength={12}
            autoComplete="new-password"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirm-password">Confirm new password</Label>
          <Input
            id="confirm-password"
            type="password"
            value={pwForm.confirm}
            onChange={(e) => setPwForm((f) => ({ ...f, confirm: e.target.value }))}
            required
            autoComplete="new-password"
          />
        </div>
        <Button type="submit" disabled={savingPw}>
          {savingPw ? "Changing…" : "Change password"}
        </Button>
      </form>

      <hr className="border-border" />

      {/* Change email */}
      <form onSubmit={handleChangeEmail} className="space-y-4">
        <div>
          <h2 className="text-base font-semibold">Change email</h2>
          <p className="text-sm text-muted-foreground">A verification link will be sent to your new address.</p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="email-password">Current password</Label>
          <Input
            id="email-password"
            type="password"
            value={emailForm.password}
            onChange={(e) => setEmailForm((f) => ({ ...f, password: e.target.value }))}
            required
            autoComplete="current-password"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="new-email">New email address</Label>
          <Input
            id="new-email"
            type="email"
            value={emailForm.newEmail}
            onChange={(e) => setEmailForm((f) => ({ ...f, newEmail: e.target.value }))}
            required
            autoComplete="email"
          />
        </div>
        <Button type="submit" disabled={savingEmail}>
          {savingEmail ? "Sending…" : "Request email change"}
        </Button>
      </form>
    </div>
  );
}

function SessionsTab() {
  const { toast } = useToast();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [revoking, setRevoking] = useState<string | null>(null);

  async function load() {
    try {
      const r = await profileApi.getSessions();
      setSessions(r.data);
    } catch {
      toast({ title: "Could not load sessions", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleRevoke(id: string) {
    setRevoking(id);
    try {
      await profileApi.revokeSession(id);
      setSessions((s) => s.filter((sess) => sess.id !== id));
      toast({ title: "Session revoked" });
    } catch {
      toast({ title: "Could not revoke session", variant: "destructive" });
    } finally {
      setRevoking(null);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading sessions…</p>;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">Active sessions</h2>
        <p className="text-sm text-muted-foreground">Sessions currently signed in to your account.</p>
      </div>
      {sessions.length === 0 ? (
        <p className="text-sm text-muted-foreground">No sessions found.</p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {sessions.map((sess) => (
            <li key={sess.id} className="flex items-start justify-between gap-4 p-4">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">
                  {sess.user_agent ?? "Unknown browser"}
                  {sess.is_current && (
                    <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
                      Current
                    </span>
                  )}
                </p>
                <p className="text-xs text-muted-foreground">
                  {sess.ip_address ?? "Unknown IP"} · Last used{" "}
                  {new Date(sess.last_used_at).toLocaleDateString()}
                </p>
              </div>
              {!sess.is_current && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={revoking === sess.id}
                  onClick={() => handleRevoke(sess.id)}
                >
                  {revoking === sess.id ? "Revoking…" : "Revoke"}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AccountTab() {
  const { user, refresh } = useAuthContext();
  const { toast } = useToast();
  const [deleteForm, setDeleteForm] = useState({ password: "", confirmation: "" });
  const [showDelete, setShowDelete] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      const r = await profileApi.exportData();
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "axonweave-data-export.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast({ title: "Export failed", variant: "destructive" });
    } finally {
      setExporting(false);
    }
  }

  async function handleDeleteConfirm() {
    if (deleteForm.confirmation !== "DELETE") {
      toast({ title: 'Type DELETE to confirm', variant: "destructive" });
      return;
    }
    setDeleting(true);
    try {
      await profileApi.deleteAccount({ current_password: deleteForm.password, confirmation: "DELETE" });
      await refresh();
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Could not delete account.";
      toast({ title: "Error", description: msg, variant: "destructive" });
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-8">
      {/* Export data */}
      <div className="space-y-3">
        <div>
          <h2 className="text-base font-semibold">Export your data</h2>
          <p className="text-sm text-muted-foreground">Download a copy of your account data in JSON format.</p>
        </div>
        <Button variant="outline" onClick={handleExport} disabled={exporting || !user?.is_verified}>
          {exporting ? "Exporting…" : "Export data"}
        </Button>
        {!user?.is_verified && (
          <p className="text-xs text-muted-foreground">Email verification required to export data.</p>
        )}
      </div>

      <hr className="border-border" />

      {/* Delete account */}
      <div className="space-y-3">
        <div>
          <h2 className="text-base font-semibold text-destructive">Delete account</h2>
          <p className="text-sm text-muted-foreground">
            Permanently delete your account and all data. This cannot be undone.
          </p>
        </div>
        <Button
          variant="destructive"
          onClick={() => setShowDelete(true)}
          disabled={!user?.is_verified}
        >
          Delete account
        </Button>
        {!user?.is_verified && (
          <p className="text-xs text-muted-foreground">Email verification required to delete account.</p>
        )}
      </div>

      {showDelete && (
        <div className="space-y-4 rounded-lg border border-destructive/50 bg-destructive/5 p-4">
          <p className="text-sm font-medium text-destructive">
            This will permanently delete your account and all workspaces, subjects, folders, and chapters.
          </p>
          <div className="space-y-2">
            <Label htmlFor="delete-password">Current password</Label>
            <Input
              id="delete-password"
              type="password"
              value={deleteForm.password}
              onChange={(e) => setDeleteForm((f) => ({ ...f, password: e.target.value }))}
              autoComplete="current-password"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="delete-confirm">Type DELETE to confirm</Label>
            <Input
              id="delete-confirm"
              value={deleteForm.confirmation}
              onChange={(e) => setDeleteForm((f) => ({ ...f, confirmation: e.target.value }))}
              placeholder="DELETE"
            />
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setShowDelete(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleting || deleteForm.confirmation !== "DELETE"}
              onClick={handleDeleteConfirm}
            >
              {deleting ? "Deleting…" : "Delete my account"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("appearance");

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "appearance", label: "Appearance" },
    { id: "learning", label: "Learning" },
    { id: "security", label: "Security" },
    { id: "sessions", label: "Sessions" },
    { id: "account", label: "Account" },
  ];

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">Manage your account and preferences.</p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-border pb-0">
        {tabs.map((t) => (
          <TabButton key={t.id} active={tab === t.id} onClick={() => setTab(t.id)}>
            {t.label}
          </TabButton>
        ))}
      </div>

      {/* Tab content */}
      <div className="rounded-lg border border-border bg-card p-6">
        {tab === "appearance" && <AppearanceTab />}
        {tab === "learning" && <LearningTab />}
        {tab === "security" && <SecurityTab />}
        {tab === "sessions" && <SessionsTab />}
        {tab === "account" && <AccountTab />}
      </div>
    </div>
  );
}
