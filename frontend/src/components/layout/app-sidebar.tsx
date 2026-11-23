"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderOpen,
  BookOpen,
  Clock,
  Archive,
  Settings,
  HelpCircle,
  BrainCircuit,
  FlaskConical,
  ClipboardCheck,
  RotateCcw,
  Library,
  Network,
  Gauge,
  Sparkles,
  Star,
  ChevronLeft,
  ChevronRight,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { openCommandPalette } from "@/features/learning-spaces/command-palette-events";
import { CurrentSpaceCard } from "@/features/learning-spaces/current-space-card";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
  disabled?: boolean;
}

/** Managing the academic environment. */
const workspaceNav: NavItem[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { label: "My Workspace", href: "/workspaces", icon: FolderOpen },
  { label: "Subjects", href: "/subjects", icon: BookOpen },
  { label: "Library", href: "/library", icon: Library },
  { label: "Study materials", href: "/study", icon: Sparkles },
  { label: "Recent Activity", href: "/activity", icon: Clock },
  { label: "Archived Items", href: "/archived", icon: Archive },
];

/**
 * Learning tools at workspace scope (across all subjects). Inside a subject, folder or chapter the
 * same tools are tabs of that learning environment and already know the context.
 */
const toolsNav: NavItem[] = [
  { label: "AI Tutor", href: "/ai-tutor", icon: BrainCircuit },
  { label: "Knowledge Graph", href: "/knowledge", icon: Network },
  { label: "Learner Intelligence", href: "/insights", icon: Gauge },
  { label: "Research Studio", href: "/research", icon: FlaskConical },
  { label: "Revision", href: "/revision", icon: RotateCcw },
  { label: "Progress", href: "/progress", icon: ClipboardCheck },
];

export const primaryNav: NavItem[] = [...workspaceNav, ...toolsNav];

const comingSoonNav: NavItem[] = [
  { label: "Favourites", href: "#", icon: Star, disabled: true },
];

const bottomNav: NavItem[] = [
  { label: "Settings", href: "/settings", icon: Settings },
  { label: "Help & Support", href: "/help", icon: HelpCircle },
];

const underPath = (pathname: string, base: string) =>
  pathname === base || pathname.startsWith(`${base}/`);

/** Subject pages live at /workspaces/{id}/subjects/..., which belongs to Subjects, not My Workspace. */
const isSubjectPath = (pathname: string) =>
  underPath(pathname, "/subjects") || /^\/workspaces\/[^/]+\/subjects(\/|$)/.test(pathname);

export function isNavActive(pathname: string, href: string): boolean {
  if (href === "#") return false;
  if (href === "/subjects") return isSubjectPath(pathname);
  if (href === "/workspaces") return underPath(pathname, href) && !isSubjectPath(pathname);
  if (href === "/library") return underPath(pathname, href) || underPath(pathname, "/documents");
  return underPath(pathname, href);
}

interface AppSidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  className?: string;
}

export function AppSidebar({ collapsed, onToggle, className }: AppSidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "border-border bg-sidebar text-sidebar-foreground flex h-full flex-col border-r transition-all duration-200",
        collapsed ? "w-14" : "w-60",
        className,
      )}
    >
      {/* Brand */}
      <div className="border-border flex h-14 items-center justify-between border-b px-3">
        {!collapsed && <span className="text-sm font-semibold tracking-tight">Axonweave</span>}
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto h-7 w-7 shrink-0"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>

      {/* Search, and the learning space the learner was last in */}
      <div className="space-y-2 px-2 pt-3">
        <button
          type="button"
          onClick={() => openCommandPalette()}
          aria-label="Quick search"
          className={cn(
            "border-border bg-background text-muted-foreground hover:text-foreground focus-visible:ring-ring flex h-8 w-full items-center gap-2 rounded-md border text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none",
            collapsed ? "justify-center" : "px-2",
          )}
        >
          <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
          {!collapsed && (
            <>
              <span className="flex-1 text-left">Search…</span>
              <kbd className="rounded border px-1 text-[10px]">Ctrl K</kbd>
            </>
          )}
        </button>
        {!collapsed && <CurrentSpaceCard pathname={pathname} />}
      </div>

      {/* Primary nav */}
      <nav className="flex-1 overflow-y-auto py-3" aria-label="Main">
        {!collapsed && <GroupLabel>Workspace</GroupLabel>}
        <NavSection items={workspaceNav} collapsed={collapsed} pathname={pathname} />

        <div className="border-border mx-3 my-3 border-t" />
        {!collapsed && <GroupLabel>Learning tools · all subjects</GroupLabel>}
        <NavSection items={toolsNav} collapsed={collapsed} pathname={pathname} />

        <div className="border-border mx-3 my-3 border-t" />

        {/* Coming soon */}
        {!collapsed && <GroupLabel>Coming soon</GroupLabel>}
        <NavSection items={comingSoonNav} collapsed={collapsed} pathname={pathname} />
      </nav>

      {/* Bottom nav */}
      <div className="border-border border-t py-3">
        <NavSection items={bottomNav} collapsed={collapsed} pathname={pathname} />
      </div>
    </aside>
  );
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-muted-foreground mb-1 px-3 text-[10px] font-semibold tracking-widest uppercase">
      {children}
    </p>
  );
}

function NavSection({
  items,
  collapsed,
  pathname,
}: {
  items: NavItem[];
  collapsed: boolean;
  pathname: string;
}) {
  return (
    <ul className="space-y-0.5 px-2">
      {items.map((item) => {
        const active = !item.disabled && isNavActive(pathname, item.href);
        const Icon = item.icon;
        return (
          <li key={item.href + item.label}>
            <Link
              href={item.disabled ? "#" : item.href}
              aria-disabled={item.disabled}
              aria-current={active ? "page" : undefined}
              tabIndex={item.disabled ? -1 : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors",
                active
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                item.disabled && "pointer-events-none opacity-40",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed && (
                <span className="truncate">
                  {item.label}
                  {item.disabled && (
                    <span className="text-muted-foreground ml-1.5 text-[10px]">(soon)</span>
                  )}
                </span>
              )}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
