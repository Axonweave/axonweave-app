"use client";

import { Bell, Menu, LogOut, User as UserIcon, Settings } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuthContext } from "@/contexts/auth-context";
import { api } from "@/lib/api/client";

interface AppHeaderProps {
  onMenuClick: () => void;
  breadcrumbs?: Array<{ label: string; href?: string }>;
}

export function AppHeader({ onMenuClick, breadcrumbs }: AppHeaderProps) {
  const { user, refresh } = useAuthContext();
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      await refresh();
      router.push("/login");
    }
  };

  const initials = user?.profile?.full_name
    ? user.profile.full_name
        .split(" ")
        .slice(0, 2)
        .map((n) => n[0])
        .join("")
        .toUpperCase()
    : user?.email?.[0]?.toUpperCase() ?? "?";

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-4">
      {/* Mobile menu toggle */}
      <Button variant="ghost" size="icon" className="h-8 w-8 md:hidden" onClick={onMenuClick}>
        <Menu className="h-4 w-4" />
        <span className="sr-only">Open menu</span>
      </Button>

      {/* Breadcrumbs */}
      <nav className="flex flex-1 items-center gap-1 text-sm text-muted-foreground" aria-label="Breadcrumb">
        {breadcrumbs?.map((crumb, i) => (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <span>/</span>}
            {crumb.href ? (
              <a href={crumb.href} className="hover:text-foreground">
                {crumb.label}
              </a>
            ) : (
              <span className="text-foreground font-medium">{crumb.label}</span>
            )}
          </span>
        ))}
      </nav>

      {/* Notifications — D-27: placeholder, disabled */}
      <Button variant="ghost" size="icon" className="h-8 w-8" disabled aria-label="Notifications">
        <Bell className="h-4 w-4" />
      </Button>

      {/* Profile menu */}
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="ghost" className="h-8 w-8 rounded-full bg-accent p-0 text-xs font-semibold" aria-label="Open profile menu" />}>
          {initials}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <div className="px-2 py-1.5">
            <p className="text-sm font-medium truncate">{user?.profile?.full_name ?? "—"}</p>
            <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
          </div>
          <DropdownMenuSeparator />
          <DropdownMenuItem render={<a href="/settings/profile" />}>
            <UserIcon className="mr-2 h-4 w-4" />
            Profile
          </DropdownMenuItem>
          <DropdownMenuItem render={<a href="/settings" />}>
            <Settings className="mr-2 h-4 w-4" />
            Settings
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive">
            <LogOut className="mr-2 h-4 w-4" />
            Log out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
