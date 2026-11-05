/**
 * API types — generated from backend OpenAPI schema via scripts/generate-types.ts.
 * Run: npm run generate-types
 *
 * These are hand-written stubs until A1 is merged and openapi.json is available.
 * Regenerate after any backend schema change.
 */

export interface UserProfile {
  full_name: string;
  avatar_url: string | null;
  preferred_language: string;
  timezone: string;
}

export interface User {
  id: string;
  email: string;
  is_verified: boolean;
  status: "pending_verification" | "active" | "suspended" | "deactivated" | "deletion_requested";
  created_at: string;
  profile: UserProfile | null;
}

export interface RegisterRequest {
  full_name: string;
  email: string;
  password: string;
  confirm_password: string;
  terms_accepted: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
  remember_me?: boolean;
}

export interface UserPreferences {
  theme: "light" | "dark" | "system";
  explanation_style: string | null;
  academic_level: string | null;
  preferred_language: string;
}

export interface SessionInfo {
  id: string;
  user_agent: string | null;
  ip_address: string | null;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface UpdateProfileRequest {
  full_name?: string;
  avatar_url?: string | null;
  timezone?: string;
  preferred_language?: string;
}

export interface UpdatePreferencesRequest {
  theme?: "light" | "dark" | "system";
  explanation_style?: string | null;
  academic_level?: string | null;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface ChangeEmailRequest {
  current_password: string;
  new_email: string;
}

export interface DeleteAccountRequest {
  password: string;
  confirmation: string;
}

export type WorkspaceType =
  | "university"
  | "personal_learning"
  | "research"
  | "professional_development"
  | "custom";

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  workspace_type: WorkspaceType;
  icon: string | null;
  colour: string | null;
  is_default: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateWorkspaceRequest {
  name: string;
  description?: string | null;
  workspace_type?: WorkspaceType;
  icon?: string | null;
  colour?: string | null;
}

export interface UpdateWorkspaceRequest {
  name?: string;
  description?: string | null;
  workspace_type?: WorkspaceType;
  icon?: string | null;
  colour?: string | null;
}

// ---- Dashboard (derived from the generated OpenAPI types; never hand-copied) ----
import type { components } from "./api.generated";

export type ActivityItem = components["schemas"]["ActivityItem"];
export type DashboardStats = components["schemas"]["DashboardStats"];
export type WorkspaceOverviewItem = components["schemas"]["WorkspaceOverviewItem"];
export type RecentSubjectItem = components["schemas"]["RecentSubjectItem"];
export type ArchivedItem = components["schemas"]["ArchivedItem"];

// ---- Academic structure (derived from the generated OpenAPI types) ----
export type Subject = components["schemas"]["SubjectOut"];
export type CreateSubjectRequest = components["schemas"]["CreateSubjectRequest"];
export type UpdateSubjectRequest = components["schemas"]["UpdateSubjectRequest"];
export type Folder = components["schemas"]["FolderOut"];
export type CreateFolderRequest = components["schemas"]["CreateFolderRequest"];
export type UpdateFolderRequest = components["schemas"]["UpdateFolderRequest"];
export type Chapter = components["schemas"]["ChapterOut"];
export type CreateChapterRequest = components["schemas"]["CreateChapterRequest"];
export type UpdateChapterRequest = components["schemas"]["UpdateChapterRequest"];
export type ChapterStatus = "not_started" | "in_progress" | "completed";
