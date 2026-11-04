import type { ActivityItem } from "@/types/api";

const VERBS: Record<string, string> = {
  created: "Created",
  updated: "Updated",
  archived: "Archived",
  restored: "Restored",
  deleted: "Deleted",
};

/** "Created workspace “Uni”" — built from real log fields only. */
export function describeActivity(
  item: Pick<ActivityItem, "action" | "entity_type" | "entity_name">,
): string {
  const verb = VERBS[item.action] ?? item.action.charAt(0).toUpperCase() + item.action.slice(1);
  const name = item.entity_name ? ` “${item.entity_name}”` : "";
  return `${verb} ${item.entity_type}${name}`;
}

/** Where an activity row can link to, or null when the entity no longer exists. */
export function activityHref(
  item: Pick<ActivityItem, "entity_type" | "entity_status">,
): string | null {
  if (item.entity_status === "deleted") return null;
  if (item.entity_status === "archived") return "/archived";
  return item.entity_type === "workspace" ? "/workspaces" : "/subjects";
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
}
