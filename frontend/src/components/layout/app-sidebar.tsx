"use client";

import { useState, useSyncExternalStore } from "react";
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
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { openCommandPalette } from "@/features/learning-spaces/command-palette-events";
import { SidebarWorkspace } from "@/features/workspaces/sidebar-workspace";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
  disabled?: boolean;
}

const homeNav: NavItem[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { label: "AI Tutor", href: "/ai-tutor", icon: BrainCircuit },
];

/** Everything uploaded or generated, across all rooms. */
const libraryNav: NavItem[] = [
  { label: "Library", href: "/library", icon: Library },
  { label: "Study materials", href: "/study", icon: Sparkles },
];

/**
 * Learning tools across every room. Inside a study room the same tools sit beside the chat and
 * already know the room, so these are for looking at everything at once.
 */
const toolsNav: NavItem[] = [
  { label: "Knowledge Graph", href: "/knowledge", icon: Network },
  { label: "Learner Intelligence", href: "/insights", icon: Gauge },
  { label: "Research Studio", href: "/research", icon: FlaskConical },
  { label: "Revision", href: "/revision", icon: RotateCcw },
  { label: "Progress", href: "/progress", icon: ClipboardCheck },
];

/** Managing workspaces and rooms, history and the bin. */
const moreNav: NavItem[] = [
  { label: "My Workspace", href: "/workspaces", icon: FolderOpen },
  { label: "Subjects", href: "/subjects", icon: BookOpen },
  { label: "Recent Activity", href: "/activity", icon: Clock },
  { label: "Archived Items", href: "/archived", icon: Archive },
];

export const primaryNav: NavItem[] = [...homeNav, ...libraryNav, ...toolsNav, ...moreNav];

const comingSoonNav: NavItem[] = [{ label: "Favourites", href: "#", icon: Star, disabled: true }];

const bottomNav: NavItem[] = [
  { label: "Settings", href: "/settings", icon: Settings },
  { label: "Help & Support", href: "/help", icon: HelpCircle },
];

const underPath = (pathname: string, base: string) =>
  pathname === base || pathname.startsWith(`${base}/`);

/**
 * Rooms and their subject pages are highlighted in the room list at the top of the sidebar, so
 * "My Workspace" lights up only on the workspaces list itself and "Subjects" only on /subjects.
 */
export function isNavActive(pathname: string, href: string): boolean {
  if (href === "#") return false;
  if (href === "/workspaces") return pathname === "/workspaces";
  if (href === "/library") return underPath(pathname, href) || underPath(pathname, "/documents");
  return underPath(pathname, href);
}

// ── Foldable groups ──────────────────────────────────────────────────────────

const GROUPS_KEY = "axonweave.sidebar-groups.v1";
const GROUPS_EVENT = "axonweave:sidebar-groups";
type GroupId = "library" | "tools" | "more";
const DEFAULT_OPEN: Record<GroupId, boolean> = { library: true, tools: false, more: false };

function readGroups(): string {
  try {
    return window.localStorage.getItem(GROUPS_KEY) ?? "";
  } catch {
    return "";
  }
}
function subscribeGroups(cb: () => void) {
  window.addEventListener(GROUPS_EVENT, cb);
  return () => window.removeEventListener(GROUPS_EVENT, cb);
}
function parseGroups(raw: string): Partial<Record<GroupId, boolean>> {
  try {
    const v: unknown = raw ? JSON.parse(raw) : {};
    return v && typeof v === "object" ? (v as Partial<Record<GroupId, boolean>>) : {};
  } catch {
    return {};
  }
}

/** Open/closed per group, remembered in this browser only. */
function useGroups() {
  const raw = useSyncExternalStore(subscribeGroups, readGroups, () => "");
  const saved = parseGroups(raw);
  const isOpen = (id: GroupId) => saved[id] ?? DEFAULT_OPEN[id];
  const toggle = (id: GroupId) => {
    try {
      window.localStorage.setItem(GROUPS_KEY, JSON.stringify({ ...saved, [id]: !isOpen(id) }));
    } catch {
      /* storage unavailable: nothing to remember */
    }
    window.dispatchEvent(new Event(GROUPS_EVENT));
  };
  return { isOpen, toggle };
}

interface AppSidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  className?: string;
}

export function AppSidebar({ collapsed, onToggle, className }: AppSidebarProps) {
  const pathname = usePathname();
  const groups = useGroups();

  const group = (id: GroupId, label: string, items: NavItem[], extra?: React.ReactNode) => {
    // a group holding the page you are on is always open, so the highlight is never hidden
    const holdsActive = items.some((i) => !i.disabled && isNavActive(pathname, i.href));
    return (
      <NavGroup
        id={id}
        label={label}
        open={collapsed || holdsActive || groups.isOpen(id)}
        canToggle={!collapsed && !holdsActive}
        onToggle={() => groups.toggle(id)}
        collapsed={collapsed}
      >
        <NavSection items={items} collapsed={collapsed} pathname={pathname} />
        {extra}
      </NavGroup>
    );
  };

  return (
    <aside
      className={cn(
        "border-border bg-sidebar text-sidebar-foreground flex h-full flex-col border-r transition-[width] duration-200",
        collapsed ? "w-14" : "w-64",
        className,
      )}
    >
      {/* Brand */}
      <div className="flex h-14 items-center justify-between px-3">
        {!collapsed && (
          <span className="flex items-center gap-2">
            <span
              className="bg-foreground text-background flex h-6 w-6 items-center justify-center rounded-md text-[11px] font-semibold"
              aria-hidden="true"
            >
              A
            </span>
            <span className="text-sm font-semibold tracking-tight">Axonweave</span>
          </span>
        )}
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

      <div className="flex-1 space-y-4 overflow-y-auto px-2 pb-3">
        {/* Where you are: the workspace and its study rooms */}
        <SidebarWorkspace pathname={pathname} collapsed={collapsed} />

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

        <nav className="space-y-3" aria-label="Main">
          <NavSection items={homeNav} collapsed={collapsed} pathname={pathname} />
          {group("library", "Library", libraryNav)}
          {group("tools", "Tools across all rooms", toolsNav)}
          {group(
            "more",
            "More",
            moreNav,
            <>
              {!collapsed && (
                <p className="text-muted-foreground mt-2 px-3 text-[10px] font-semibold tracking-widest uppercase">
                  Coming soon
                </p>
              )}
              <NavSection items={comingSoonNav} collapsed={collapsed} pathname={pathname} />
            </>,
          )}
        </nav>
      </div>

      {/* Bottom nav */}
      <div className="border-border border-t px-2 py-3">
        <NavSection items={bottomNav} collapsed={collapsed} pathname={pathname} />
      </div>
    </aside>
  );
}

function NavGroup({
  id,
  label,
  open,
  canToggle,
  onToggle,
  collapsed,
  children,
}: {
  id: string;
  label: string;
  open: boolean;
  canToggle: boolean;
  onToggle: () => void;
  collapsed: boolean;
  children: React.ReactNode;
}) {
  const [regionId] = useState(() => `nav-group-${id}`);
  if (collapsed) return <div className="border-border border-t pt-3">{children}</div>;
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        disabled={!canToggle}
        aria-expanded={open}
        aria-controls={regionId}
        className="text-muted-foreground hover:text-foreground focus-visible:ring-ring flex w-full items-center justify-between rounded-md px-3 py-1 text-xs font-semibold transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:cursor-default disabled:hover:text-current"
      >
        {label}
        {canToggle ? (
          <ChevronDown
            className={cn("h-3.5 w-3.5 transition-transform duration-200", !open && "-rotate-90")}
            aria-hidden="true"
          />
        ) : null}
      </button>
      <div
        id={regionId}
        className={cn(
          "grid transition-[grid-template-rows,opacity] duration-200 ease-out",
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
        )}
        inert={!open}
      >
        <div className="overflow-hidden pt-1">{children}</div>
      </div>
    </div>
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
    <ul className="space-y-0.5">
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
                "flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition-colors",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-foreground",
                item.disabled && "pointer-events-none opacity-40",
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  active ? "text-foreground" : "text-muted-foreground",
                )}
              />
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
