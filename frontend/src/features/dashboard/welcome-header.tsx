"use client";

import { useAuthContext } from "@/contexts/auth-context";

export function WelcomeHeader() {
  const { user, loading } = useAuthContext();
  const name = user?.profile?.full_name?.trim() || user?.email || "";

  return (
    <header className="space-y-1">
      {loading ? (
        <div
          role="status"
          aria-label="Loading"
          className="bg-muted h-8 w-64 animate-pulse rounded"
        />
      ) : (
        <h1 className="text-foreground text-2xl font-semibold break-words">
          {name ? `Welcome back, ${name}` : "Welcome back"}
        </h1>
      )}
      <p className="text-muted-foreground text-sm">
        Your workspaces, subjects and recent work in one place.
      </p>
    </header>
  );
}
