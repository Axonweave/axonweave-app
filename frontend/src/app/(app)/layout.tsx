"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AuthProvider, useAuthContext } from "@/contexts/auth-context";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { AppHeader } from "@/components/layout/app-header";
import { MobileNav } from "@/components/layout/mobile-nav";
import { LoadingPage } from "@/components/ui/loading";
import { Toaster } from "@/components/ui/toaster";
import { CommandPalette } from "@/features/learning-spaces/command-palette";

function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuthContext();
  const router = useRouter();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [user, loading, router]);

  if (loading) return <LoadingPage />;
  if (!user) return null; // redirect in progress

  return (
    <div className="bg-sidebar flex h-screen overflow-hidden">
      {/* Desktop sidebar */}
      <AppSidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
        className="hidden md:flex"
      />

      {/* Mobile drawer */}
      <MobileNav open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

      {/* Main area */}
      {/* Main area: an inset panel that sits on the sidebar colour, so the two read as separate surfaces */}
      <div className="bg-background flex min-w-0 flex-1 flex-col overflow-hidden md:my-2 md:mr-2 md:rounded-xl md:border md:shadow-[0_1px_2px_rgb(15_23_20/0.04),0_12px_32px_-16px_rgb(15_23_20/0.12)]">
        <AppHeader onMenuClick={() => setMobileNavOpen(true)} />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>

      <Toaster />
      <CommandPalette />
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  );
}
